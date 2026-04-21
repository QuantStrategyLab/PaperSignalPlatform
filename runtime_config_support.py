from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from quant_platform_kit.common.runtime_config import (
    first_non_empty,
    resolve_strategy_runtime_path_settings,
)
from strategy_registry import PAPER_SIGNAL_PLATFORM, resolve_strategy_definition, resolve_strategy_metadata
from us_equity_strategies import get_strategy_catalog

DEFAULT_PAPER_ACCOUNT_GROUP = "default"


@dataclass(frozen=True)
class PaperAccountGroupConfig:
    service_name: str | None = None
    account_alias: str | None = None
    base_currency: str | None = None
    market_calendar: str | None = None
    starting_equity: float | None = None
    slippage_bps: float | None = None
    commission_bps: float | None = None
    fill_model: str | None = None
    artifact_bucket_prefix: str | None = None
    telegram_chat_id: str | None = None


@dataclass(frozen=True)
class PlatformRuntimeSettings:
    project_id: str | None
    strategy_profile: str
    strategy_display_name: str
    strategy_domain: str
    strategy_target_mode: str | None
    strategy_artifact_root: str | None
    strategy_artifact_dir: str | None
    feature_snapshot_path: str | None
    feature_snapshot_manifest_path: str | None
    strategy_config_path: str | None
    strategy_config_source: str | None
    reconciliation_output_path: str | None
    paper_account_group: str
    service_name: str | None
    account_alias: str
    base_currency: str
    market_calendar: str
    starting_equity: float
    slippage_bps: float
    commission_bps: float
    fill_model: str
    artifact_bucket_prefix: str | None
    state_store_backend: str
    artifact_store_backend: str
    state_dir: str
    artifact_dir: str
    market_data_provider: str
    history_lookback_days: int
    tg_token: str | None
    tg_chat_id: str | None
    notify_lang: str


def load_platform_runtime_settings(
    *,
    project_id_resolver: Callable[[], str | None],
    secret_client_factory: Callable[[], Any] | None = None,
) -> PlatformRuntimeSettings:
    project_id = project_id_resolver()
    strategy_definition = resolve_strategy_definition(
        os.getenv("STRATEGY_PROFILE"),
        platform_id=PAPER_SIGNAL_PLATFORM,
    )
    strategy_metadata = resolve_strategy_metadata(
        strategy_definition.profile,
        platform_id=PAPER_SIGNAL_PLATFORM,
    )
    runtime_paths = resolve_strategy_runtime_path_settings(
        strategy_catalog=get_strategy_catalog(),
        strategy_definition=strategy_definition,
        strategy_metadata=strategy_metadata,
        platform_env_prefix="PAPER_SIGNAL",
        env=os.environ,
        repo_root=Path(__file__).resolve().parent,
        include_reconciliation_output=True,
    )
    paper_account_group = resolve_paper_account_group(os.getenv("PAPER_ACCOUNT_GROUP"))
    group_config = load_paper_account_group_config(
        project_id=project_id,
        paper_account_group=paper_account_group,
        raw_json=os.getenv("PAPER_ACCOUNT_GROUP_CONFIG_JSON"),
        secret_name=os.getenv("PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME"),
        secret_client_factory=secret_client_factory,
    )
    return PlatformRuntimeSettings(
        project_id=project_id,
        strategy_profile=runtime_paths.strategy_profile,
        strategy_display_name=runtime_paths.strategy_display_name,
        strategy_domain=runtime_paths.strategy_domain,
        strategy_target_mode=runtime_paths.strategy_target_mode,
        strategy_artifact_root=runtime_paths.strategy_artifact_root,
        strategy_artifact_dir=runtime_paths.strategy_artifact_dir,
        feature_snapshot_path=runtime_paths.feature_snapshot_path,
        feature_snapshot_manifest_path=runtime_paths.feature_snapshot_manifest_path,
        strategy_config_path=runtime_paths.strategy_config_path,
        strategy_config_source=runtime_paths.strategy_config_source,
        reconciliation_output_path=runtime_paths.reconciliation_output_path,
        paper_account_group=paper_account_group,
        service_name=group_config.service_name,
        account_alias=require_group_string(
            group_config.account_alias,
            field_name="account_alias",
            paper_account_group=paper_account_group,
        ),
        base_currency=require_group_string(
            group_config.base_currency,
            field_name="base_currency",
            paper_account_group=paper_account_group,
        ),
        market_calendar=require_group_string(
            group_config.market_calendar,
            field_name="market_calendar",
            paper_account_group=paper_account_group,
        ),
        starting_equity=require_group_float(
            group_config.starting_equity,
            field_name="starting_equity",
            paper_account_group=paper_account_group,
        ),
        slippage_bps=require_group_float(
            group_config.slippage_bps,
            field_name="slippage_bps",
            paper_account_group=paper_account_group,
        ),
        commission_bps=require_group_float(
            group_config.commission_bps,
            field_name="commission_bps",
            paper_account_group=paper_account_group,
        ),
        fill_model=require_group_string(
            group_config.fill_model,
            field_name="fill_model",
            paper_account_group=paper_account_group,
        ),
        artifact_bucket_prefix=group_config.artifact_bucket_prefix,
        state_store_backend=(os.getenv("PAPER_SIGNAL_STATE_STORE_BACKEND", "local_json").strip() or "local_json"),
        artifact_store_backend=(os.getenv("PAPER_SIGNAL_ARTIFACT_STORE_BACKEND", "local_json").strip() or "local_json"),
        state_dir=(
            os.getenv("PAPER_SIGNAL_STATE_DIR", str(Path(__file__).resolve().parent / ".paper_signal" / "state")).strip()
            or str(Path(__file__).resolve().parent / ".paper_signal" / "state")
        ),
        artifact_dir=(
            os.getenv(
                "PAPER_SIGNAL_ARTIFACT_DIR",
                str(Path(__file__).resolve().parent / ".paper_signal" / "artifacts"),
            ).strip()
            or str(Path(__file__).resolve().parent / ".paper_signal" / "artifacts")
        ),
        market_data_provider=(os.getenv("PAPER_SIGNAL_MARKET_DATA_PROVIDER", "yfinance").strip() or "yfinance"),
        history_lookback_days=int(os.getenv("PAPER_SIGNAL_HISTORY_LOOKBACK_DAYS", "420")),
        tg_token=first_non_empty(os.getenv("TELEGRAM_TOKEN"), os.getenv("TG_TOKEN")),
        tg_chat_id=first_non_empty(group_config.telegram_chat_id, os.getenv("GLOBAL_TELEGRAM_CHAT_ID")),
        notify_lang=(os.getenv("NOTIFY_LANG", "en").strip() or "en"),
    )


def resolve_paper_account_group(raw_value: str | None) -> str:
    value = (raw_value or "").strip()
    if not value:
        raise EnvironmentError("PAPER_ACCOUNT_GROUP is required")
    return value


def load_paper_account_group_config(
    *,
    project_id: str | None,
    paper_account_group: str,
    raw_json: str | None,
    secret_name: str | None,
    secret_client_factory: Callable[[], Any] | None = None,
) -> PaperAccountGroupConfig:
    payload = None
    if secret_name:
        if not project_id:
            raise EnvironmentError(
                "GOOGLE_CLOUD_PROJECT is required when PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME is set"
            )
        payload = load_secret_payload(
            project_id,
            secret_name,
            secret_client_factory=secret_client_factory,
        )
    elif raw_json:
        payload = raw_json

    if not payload:
        raise EnvironmentError(
            "PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME or PAPER_ACCOUNT_GROUP_CONFIG_JSON is required"
        )

    configs = parse_paper_account_group_configs(payload)
    if paper_account_group not in configs:
        available = ", ".join(sorted(configs))
        raise ValueError(
            f"PAPER_ACCOUNT_GROUP={paper_account_group!r} not found in paper account-group config; "
            f"available groups: {available}"
        )
    return configs[paper_account_group]


def parse_paper_account_group_configs(payload: str) -> dict[str, PaperAccountGroupConfig]:
    raw_data = json.loads(payload)
    groups = raw_data.get("groups", raw_data) if isinstance(raw_data, dict) else None
    if not isinstance(groups, dict):
        raise ValueError('Paper account-group config must be a JSON object or {"groups": {...}}')

    parsed: dict[str, PaperAccountGroupConfig] = {}
    for group_name, group_payload in groups.items():
        if not isinstance(group_payload, dict):
            raise ValueError(f"Paper account group {group_name!r} must be a JSON object")
        parsed[str(group_name)] = PaperAccountGroupConfig(
            service_name=normalize_optional_string(group_payload.get("service_name")),
            account_alias=normalize_optional_string(group_payload.get("account_alias")),
            base_currency=normalize_optional_string(group_payload.get("base_currency")),
            market_calendar=normalize_optional_string(group_payload.get("market_calendar")),
            starting_equity=parse_optional_float(group_payload.get("starting_equity")),
            slippage_bps=parse_optional_float(group_payload.get("slippage_bps")),
            commission_bps=parse_optional_float(group_payload.get("commission_bps")),
            fill_model=normalize_optional_string(group_payload.get("fill_model")),
            artifact_bucket_prefix=normalize_optional_string(group_payload.get("artifact_bucket_prefix")),
            telegram_chat_id=normalize_optional_string(group_payload.get("telegram_chat_id")),
        )
    return parsed


def load_secret_payload(
    project_id: str,
    secret_name: str,
    *,
    secret_client_factory: Callable[[], Any] | None = None,
) -> str:
    if secret_client_factory is None:
        try:
            import google.cloud.secretmanager_v1 as secret_manager
        except ImportError:
            from google.cloud import secret_manager

        secret_client_factory = secret_manager.SecretManagerServiceClient

    client = secret_client_factory()
    resource_name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": resource_name})
    return response.payload.data.decode("UTF-8")


def normalize_optional_string(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value or None


def parse_optional_float(raw_value: Any) -> float | None:
    if raw_value in (None, ""):
        return None
    return float(raw_value)


def require_group_string(
    value: str | None,
    *,
    field_name: str,
    paper_account_group: str,
) -> str:
    if value is None or not str(value).strip():
        raise EnvironmentError(
            f"paper account group {paper_account_group!r} requires non-empty {field_name}"
        )
    return str(value).strip()


def require_group_float(
    value: float | None,
    *,
    field_name: str,
    paper_account_group: str,
) -> float:
    if value is None:
        raise EnvironmentError(f"paper account group {paper_account_group!r} requires numeric {field_name}")
    return float(value)
