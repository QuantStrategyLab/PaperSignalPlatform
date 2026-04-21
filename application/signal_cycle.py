from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from quant_platform_kit.common.models import PortfolioSnapshot, Position
from quant_platform_kit.common.feature_snapshot_runtime import (
    FeatureSnapshotRuntimeSettings,
    evaluate_feature_snapshot_strategy,
)
from quant_platform_kit.strategy_contracts import StrategyContext, build_execution_timing_metadata

from application.cycle_result import SignalCycleResult
from application.market_data_service import (
    DailyBarProvider,
    build_close_history_loader,
    build_semiconductor_indicator_inputs,
    latest_available_session,
    resolve_effective_session,
)
from application.notification_service import NotificationMessage
from application.paper_execution_service import (
    PaperExecutionConfig,
    PaperExecutionPlan,
    simulate_rebalance,
)
from application.reconciliation_service import ReconciliationRecord
from application.runtime_dependencies import PaperSignalRuntimeDependencies
from application.state_store_service import PaperAccountState
from decision_mapper import map_strategy_decision
from runtime_config_support import PlatformRuntimeSettings
from strategy_runtime import LoadedStrategyRuntime


def run_paper_signal_cycle(
    *,
    settings: PlatformRuntimeSettings,
    runtime: LoadedStrategyRuntime,
    dependencies: PaperSignalRuntimeDependencies,
    market_data_provider: DailyBarProvider,
    as_of_date: str | pd.Timestamp | None = None,
) -> SignalCycleResult:
    if runtime.required_inputs not in {
        frozenset({"market_history"}),
        frozenset({"benchmark_history", "portfolio_snapshot"}),
        frozenset({"derived_indicators", "portfolio_snapshot"}),
        frozenset({"feature_snapshot"}),
    }:
        raise NotImplementedError(
            "Minimal paper cycle currently supports market_history, "
            "benchmark_history+portfolio_snapshot, and "
            "derived_indicators+portfolio_snapshot, and "
            "feature_snapshot profiles"
        )

    state = dependencies.state_store.load(settings.paper_account_group) or _bootstrap_state(settings)
    symbols = _resolve_required_symbols(runtime, state)
    requested_as_of = _normalize_as_of_date(as_of_date)
    bars_by_symbol = (
        market_data_provider.fetch_daily_bars(
            symbols,
            as_of_date=requested_as_of,
            lookback_days=settings.history_lookback_days,
        )
        if symbols
        else {}
    )
    as_of_session = latest_available_session(bars_by_symbol) if bars_by_symbol else requested_as_of

    state, execution_summary = _apply_pending_plan(
        state=state,
        as_of_session=as_of_session,
        bars_by_symbol=bars_by_symbol,
        execution_config=PaperExecutionConfig(
            fill_model=settings.fill_model,
            slippage_bps=settings.slippage_bps,
            commission_bps=settings.commission_bps,
        ),
    )

    portfolio_snapshot = _build_portfolio_snapshot(
        state=state,
        as_of_session=as_of_session,
        bars_by_symbol=bars_by_symbol,
        account_hash=settings.paper_account_group,
    )
    decision, runtime_metadata = _evaluate_strategy_decision(
        runtime=runtime,
        settings=settings,
        as_of_session=as_of_session,
        bars_by_symbol=bars_by_symbol,
        portfolio_snapshot=portfolio_snapshot,
    )
    allocation_payload, decision_metadata = map_strategy_decision(
        decision,
        strategy_profile=runtime.profile,
        runtime_metadata={
            "service_name": settings.service_name,
            **dict(runtime_metadata),
        },
    )
    pending_plan, queue_status = _queue_pending_plan(
        state=state,
        as_of_session=as_of_session,
        allocation_payload=allocation_payload,
        decision_metadata=decision_metadata,
    )
    next_state = PaperAccountState(
        paper_account_group=state.paper_account_group,
        cash=state.cash,
        nav=float(portfolio_snapshot.total_equity),
        positions=state.positions,
        metadata={
            **dict(state.metadata),
            "last_run_as_of": as_of_session.strftime("%Y-%m-%d"),
            "last_strategy_profile": runtime.profile,
            "pending_plan": pending_plan,
            "last_decision": {
                "risk_flags": tuple(str(flag) for flag in decision.risk_flags),
                "diagnostics": _json_safe(decision_metadata),
            },
        },
    )
    dependencies.state_store.save(next_state)

    summary = {
        "as_of": as_of_session.strftime("%Y-%m-%d"),
        "strategy_profile": runtime.profile,
        "paper_account_group": settings.paper_account_group,
        "nav": float(portfolio_snapshot.total_equity),
        "cash": float(next_state.cash),
        "positions": _positions_payload(portfolio_snapshot),
        "decision": _json_safe(decision_metadata),
        "allocation": _json_safe(allocation_payload),
        "execution": execution_summary,
        "queue_status": queue_status,
    }
    dependencies.artifact_writer.write_record(
        ReconciliationRecord(
            strategy_profile=runtime.profile,
            paper_account_group=settings.paper_account_group,
            payload=summary,
        )
    )
    dependencies.notification_port.publish(
        NotificationMessage(
            title=f"{runtime.profile} paper signal",
            body=_render_notification_body(summary),
            metadata={"strategy_profile": runtime.profile},
        )
    )
    return SignalCycleResult(
        status="ok",
        platform_id="paper_signal",
        strategy_profile=runtime.profile,
        paper_account_group=settings.paper_account_group,
        summary=summary,
    )


def _bootstrap_state(settings: PlatformRuntimeSettings) -> PaperAccountState:
    return PaperAccountState(
        paper_account_group=settings.paper_account_group,
        cash=float(settings.starting_equity),
        nav=float(settings.starting_equity),
        positions={},
        metadata={},
    )


def _resolve_required_symbols(
    runtime: LoadedStrategyRuntime,
    state: PaperAccountState,
) -> tuple[str, ...]:
    config = dict(runtime.entrypoint.manifest.default_config)
    pending_plan = dict((state.metadata or {}).get("pending_plan") or {})
    symbols: list[str] = []
    seen: set[str] = set()
    for source in (
        config.get("ranking_pool") or (),
        config.get("canary_assets") or (),
        config.get("managed_symbols") or (),
        (config.get("benchmark_symbol"),),
        (config.get("safe_haven"),),
        tuple((pending_plan.get("strategy_symbols") or ())),
        tuple((state.positions or {}).keys()),
    ):
        for raw_symbol in source or ():
            symbol = str(raw_symbol or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
    return tuple(symbols)


def _normalize_as_of_date(as_of_date: str | pd.Timestamp | None) -> pd.Timestamp:
    if as_of_date is None:
        return pd.Timestamp.utcnow().tz_localize(None).normalize()
    return pd.Timestamp(as_of_date).normalize()


def _evaluate_strategy_decision(
    *,
    runtime: LoadedStrategyRuntime,
    settings: PlatformRuntimeSettings,
    as_of_session: pd.Timestamp,
    bars_by_symbol: dict[str, pd.DataFrame],
    portfolio_snapshot: PortfolioSnapshot,
) -> tuple[Any, dict[str, Any]]:
    runtime_config = _build_runtime_config_inputs(
        runtime=runtime,
        settings=settings,
    )
    if runtime.required_inputs == frozenset({"feature_snapshot"}):
        signal_delay = runtime.runtime_adapter.runtime_policy.signal_effective_after_trading_days
        if signal_delay is None:
            signal_delay = 1
        snapshot_result = evaluate_feature_snapshot_strategy(
            entrypoint=runtime.entrypoint,
            runtime_adapter=runtime.runtime_adapter,
            runtime_settings=FeatureSnapshotRuntimeSettings(
                feature_snapshot_path=settings.feature_snapshot_path,
                feature_snapshot_manifest_path=settings.feature_snapshot_manifest_path,
                strategy_config_path=settings.strategy_config_path,
                strategy_config_source=settings.strategy_config_source,
                dry_run_only=False,
            ),
            runtime_config=runtime_config,
            merged_runtime_config=runtime.merged_runtime_config or runtime.entrypoint.manifest.default_config,
            as_of=as_of_session.to_pydatetime(),
            base_managed_symbols=tuple(
                str(symbol)
                for symbol in ((runtime.merged_runtime_config or {}).get("managed_symbols") or ())
            ),
            include_strategy_display_name=True,
            set_run_as_of=True,
            catch_evaluation_errors=True,
        )
        metadata = {
            **build_execution_timing_metadata(
                signal_date=as_of_session,
                signal_effective_after_trading_days=signal_delay,
            ),
            **dict(snapshot_result.metadata),
        }
        return snapshot_result.decision, metadata

    decision = runtime.entrypoint.evaluate(
        StrategyContext(
            as_of=as_of_session,
            market_data=_build_market_data_inputs(
                runtime=runtime,
                bars_by_symbol=bars_by_symbol,
            ),
            portfolio=portfolio_snapshot,
            state={"current_holdings": tuple(position.symbol for position in portfolio_snapshot.positions)},
            runtime_config=runtime_config,
        )
    )
    return decision, {}


def _apply_pending_plan(
    *,
    state: PaperAccountState,
    as_of_session: pd.Timestamp,
    bars_by_symbol: dict[str, pd.DataFrame],
    execution_config: PaperExecutionConfig,
) -> tuple[PaperAccountState, dict[str, Any]]:
    pending_plan = dict((state.metadata or {}).get("pending_plan") or {})
    if not pending_plan:
        return state, {"status": "no_pending_plan"}

    effective_session = resolve_effective_session(
        effective_date=pending_plan["effective_date"],
        bars_by_symbol=bars_by_symbol,
    )
    if effective_session is None or effective_session > as_of_session:
        return state, {"status": "pending_waiting_for_effective_session"}

    fill_prices = {}
    for symbol in pending_plan.get("strategy_symbols") or ():
        frame = bars_by_symbol.get(symbol)
        if frame is None or frame.empty or effective_session not in frame.index:
            return state, {"status": "pending_missing_fill_price", "symbol": symbol}
        fill_prices[symbol] = float(frame.loc[effective_session, "open"])

    execution_result = simulate_rebalance(
        plan=PaperExecutionPlan(
            target_mode=str(pending_plan["target_mode"]),
            targets=dict(pending_plan["targets"]),
            metadata=dict(pending_plan.get("metadata") or {}),
        ),
        config=execution_config,
        current_state={"cash": state.cash, "positions": state.positions},
        fill_prices=fill_prices,
    )
    next_state = PaperAccountState(
        paper_account_group=state.paper_account_group,
        cash=float(execution_result.metadata["cash_after"]),
        nav=state.nav,
        positions={
            row["symbol"]: {
                "quantity": float(row["quantity"]),
                "average_cost": row["average_cost"],
            }
            for row in execution_result.positions
        },
        metadata={
            **dict(state.metadata),
            "last_execution": {
                "effective_session": effective_session.strftime("%Y-%m-%d"),
                "trades": _json_safe(execution_result.trades),
                "metadata": _json_safe(execution_result.metadata),
            },
            "pending_plan": None,
        },
    )
    return next_state, {
        "status": "executed_pending_plan",
        "effective_session": effective_session.strftime("%Y-%m-%d"),
        "trade_count": len(execution_result.trades),
        "turnover_value": execution_result.metadata.get("turnover_value", 0.0),
        "commission_paid": execution_result.metadata.get("commission_paid", 0.0),
        "slippage_cost": execution_result.metadata.get("slippage_cost", 0.0),
    }


def _build_portfolio_snapshot(
    *,
    state: PaperAccountState,
    as_of_session: pd.Timestamp,
    bars_by_symbol: dict[str, pd.DataFrame],
    account_hash: str,
) -> PortfolioSnapshot:
    positions = []
    total_equity = float(state.cash)
    for symbol, payload in sorted((state.positions or {}).items()):
        frame = bars_by_symbol.get(symbol)
        if frame is None or frame.empty or as_of_session not in frame.index:
            continue
        close_price = float(frame.loc[as_of_session, "close"])
        quantity = float((payload or {}).get("quantity", 0.0) or 0.0)
        market_value = quantity * close_price
        total_equity += market_value
        positions.append(
            Position(
                symbol=symbol,
                quantity=quantity,
                market_value=market_value,
                average_cost=(payload or {}).get("average_cost"),
            )
        )
    return PortfolioSnapshot(
        as_of=as_of_session.to_pydatetime(),
        total_equity=total_equity,
        buying_power=float(state.cash),
        cash_balance=float(state.cash),
        positions=tuple(positions),
        metadata={"account_hash": account_hash},
    )


def _build_market_data_inputs(
    *,
    runtime: LoadedStrategyRuntime,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    if runtime.required_inputs == frozenset({"market_history"}):
        return {"market_history": build_close_history_loader(bars_by_symbol)}
    if runtime.required_inputs == frozenset({"benchmark_history", "portfolio_snapshot"}):
        config = dict(runtime.entrypoint.manifest.default_config)
        benchmark_symbol = str(config.get("benchmark_symbol") or "").strip().upper()
        if not benchmark_symbol:
            raise ValueError(
                f"Profile {runtime.profile!r} requires benchmark_symbol in default_config"
            )
        frame = bars_by_symbol.get(benchmark_symbol)
        if frame is None or frame.empty:
            raise ValueError(
                f"Benchmark history missing for symbol {benchmark_symbol!r}"
            )
        return {
            "benchmark_history": (
                frame[["open", "high", "low", "close", "volume"]]
                .reset_index(drop=True)
                .to_dict("records")
            )
        }
    if runtime.required_inputs == frozenset({"derived_indicators", "portfolio_snapshot"}):
        config = dict(runtime.entrypoint.manifest.default_config)
        trend_ma_window = int(config.get("trend_ma_window") or 140)
        return build_semiconductor_indicator_inputs(
            bars_by_symbol,
            trend_ma_window=trend_ma_window,
        )
    raise NotImplementedError(
        f"Unsupported required_inputs={sorted(runtime.required_inputs)}"
    )


def _build_runtime_config_inputs(
    *,
    runtime: LoadedStrategyRuntime,
    settings: PlatformRuntimeSettings,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "translator": _build_translator(settings.notify_lang),
        "signal_effective_after_trading_days": (
            runtime.runtime_adapter.runtime_policy.signal_effective_after_trading_days
        ),
    }
    if runtime.required_inputs == frozenset({"market_history"}):
        config["pacing_sec"] = 0.0
    return config


def _queue_pending_plan(
    *,
    state: PaperAccountState,
    as_of_session: pd.Timestamp,
    allocation_payload: Mapping[str, Any] | None,
    decision_metadata: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not allocation_payload:
        return None, "no_actionable_allocation"
    effective_date = str(decision_metadata.get("effective_date") or "").strip()
    if not effective_date:
        return None, "missing_effective_date"
    return (
        {
            "created_as_of": as_of_session.strftime("%Y-%m-%d"),
            "effective_date": effective_date,
            "target_mode": allocation_payload["target_mode"],
            "targets": dict(allocation_payload["targets"]),
            "strategy_symbols": tuple(allocation_payload["strategy_symbols"]),
            "metadata": {
                "signal_description": decision_metadata.get("signal_description"),
                "risk_flags": tuple(decision_metadata.get("risk_flags") or ()),
            },
        },
        "queued_pending_plan",
    )


def _positions_payload(portfolio_snapshot: PortfolioSnapshot) -> list[dict[str, Any]]:
    payload = []
    for position in portfolio_snapshot.positions:
        payload.append(
            {
                "symbol": position.symbol,
                "quantity": float(position.quantity),
                "market_value": float(position.market_value),
                "average_cost": position.average_cost,
            }
        )
    return payload


def _build_translator(lang: str):
    normalized = str(lang or "en").strip().lower()
    if normalized.startswith("zh"):
        templates = {
            "emergency": "应急防守: {safe} | n_bad={n_bad}",
            "daily_check": "每日 canary 检查，无需调仓",
            "quarterly": "季度调仓，目标持有前 {n} 名",
        }
    else:
        templates = {
            "emergency": "Emergency defense: {safe} | n_bad={n_bad}",
            "daily_check": "Daily canary check, no rebalance today",
            "quarterly": "Quarterly rebalance, top {n}",
        }

    def _translator(key: str, **kwargs):
        template = templates.get(key)
        if not template:
            if not kwargs:
                return key
            pairs = ", ".join(f"{name}={value}" for name, value in sorted(kwargs.items()))
            return f"{key}({pairs})"
        return template.format(**kwargs)

    return _translator


def _render_notification_body(summary: Mapping[str, Any]) -> str:
    allocation = summary.get("allocation") or {}
    targets = allocation.get("targets") or {}
    target_lines = ", ".join(f"{symbol}:{value:.2%}" for symbol, value in targets.items()) if allocation.get("target_mode") == "weight" else ", ".join(f"{symbol}:${value:,.2f}" for symbol, value in targets.items())
    return "\n".join(
        [
            f"as_of={summary.get('as_of')}",
            f"nav={float(summary.get('nav') or 0.0):,.2f}",
            f"cash={float(summary.get('cash') or 0.0):,.2f}",
            f"execution={summary.get('execution', {}).get('status')}",
            f"queue_status={summary.get('queue_status')}",
            f"signal={(((summary.get('decision') or {}).get('signal_description') or (summary.get('decision') or {}).get('signal_display') or '')).strip()}",
            f"targets={target_lines or 'none'}",
        ]
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value
