from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class PaperExecutionConfig:
    fill_model: str
    slippage_bps: float
    commission_bps: float


@dataclass(frozen=True)
class PaperExecutionPlan:
    target_mode: str
    targets: Mapping[str, float]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperExecutionResult:
    status: str
    trades: tuple[Mapping[str, Any], ...] = ()
    positions: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


def simulate_rebalance(
    *,
    plan: PaperExecutionPlan,
    config: PaperExecutionConfig,
    current_state: Mapping[str, Any],
    fill_prices: Mapping[str, float],
) -> PaperExecutionResult:
    if plan.target_mode not in {"weight", "value"}:
        raise ValueError(f"Unsupported paper target_mode={plan.target_mode!r}")

    cash = float(current_state.get("cash", 0.0) or 0.0)
    raw_positions = dict(current_state.get("positions") or {})
    positions = {
        symbol: {
            "quantity": float((payload or {}).get("quantity", 0.0) or 0.0),
            "average_cost": (
                float((payload or {}).get("average_cost"))
                if (payload or {}).get("average_cost") is not None
                else None
            ),
        }
        for symbol, payload in raw_positions.items()
    }

    current_values = {
        symbol: float(payload["quantity"]) * float(fill_prices.get(symbol, 0.0))
        for symbol, payload in positions.items()
    }
    total_equity = cash + sum(current_values.values())
    if total_equity <= 0.0:
        raise ValueError("Paper execution requires positive total equity")

    if plan.target_mode == "weight":
        target_values = {
            symbol: float(weight) * total_equity
            for symbol, weight in plan.targets.items()
        }
    else:
        target_values = {symbol: float(value) for symbol, value in plan.targets.items()}

    symbols = tuple(dict.fromkeys(tuple(positions) + tuple(target_values)))
    trade_rows: list[dict[str, Any]] = []
    turnover_value = 0.0
    commission_paid = 0.0
    slippage_cost = 0.0

    def _commission(notional: float) -> float:
        return abs(float(notional)) * float(config.commission_bps) / 10000.0

    for side in ("sell", "buy"):
        for symbol in symbols:
            fill_price = float(fill_prices.get(symbol, 0.0) or 0.0)
            if fill_price <= 0.0:
                continue
            current_value = float(current_values.get(symbol, 0.0))
            target_value = float(target_values.get(symbol, 0.0))
            diff_value = target_value - current_value
            if side == "sell" and diff_value >= 0.0:
                continue
            if side == "buy" and diff_value <= 0.0:
                continue

            position = positions.setdefault(symbol, {"quantity": 0.0, "average_cost": None})
            open_price = fill_price
            if side == "sell":
                executed_price = open_price * (1.0 - float(config.slippage_bps) / 10000.0)
                quantity = min(float(position["quantity"]), abs(diff_value) / open_price)
                notional = quantity * executed_price
                commission = _commission(notional)
                position["quantity"] = float(position["quantity"]) - quantity
                cash += notional - commission
                slippage_cost += quantity * (open_price - executed_price)
            else:
                executed_price = open_price * (1.0 + float(config.slippage_bps) / 10000.0)
                quantity = abs(diff_value) / executed_price
                notional = quantity * executed_price
                commission = _commission(notional)
                prior_qty = float(position["quantity"])
                prior_cost = float(position["average_cost"] or 0.0)
                new_qty = prior_qty + quantity
                if new_qty > 0.0:
                    position["average_cost"] = (
                        ((prior_qty * prior_cost) + (quantity * executed_price)) / new_qty
                    )
                position["quantity"] = new_qty
                cash -= notional + commission
                slippage_cost += quantity * (executed_price - open_price)

            turnover_value += abs(notional)
            commission_paid += commission
            current_values[symbol] = float(position["quantity"]) * open_price
            if abs(float(position["quantity"])) < 1e-12:
                position["quantity"] = 0.0
                position["average_cost"] = None
            trade_rows.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "fill_price": executed_price,
                    "notional": notional,
                    "commission": commission,
                }
            )

    output_positions = []
    for symbol in sorted(positions):
        payload = positions[symbol]
        quantity = float(payload["quantity"])
        if abs(quantity) < 1e-12:
            continue
        output_positions.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "average_cost": payload["average_cost"],
            }
        )

    return PaperExecutionResult(
        status="executed",
        trades=tuple(trade_rows),
        positions=tuple(output_positions),
        metadata={
            "cash_after": cash,
            "total_equity_before": total_equity,
            "turnover_value": turnover_value,
            "commission_paid": commission_paid,
            "slippage_cost": slippage_cost,
        },
    )
