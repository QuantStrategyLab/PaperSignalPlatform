from __future__ import annotations

import json
from dataclasses import dataclass, field

from application.operator_support import (
    format_paper_account_state,
    list_gcs_reconciliation_records,
    list_local_reconciliation_records,
    load_latest_gcs_reconciliation_record,
    load_latest_local_reconciliation_record,
)
from application.state_store_service import PaperAccountState


@dataclass
class FakeListBlob:
    name: str
    payload: dict

    def download_as_text(self) -> str:
        return json.dumps(self.payload)


@dataclass
class FakeListStorageClient:
    blobs: dict[str, list[FakeListBlob]] = field(default_factory=dict)

    def list_blobs(self, bucket_name: str, prefix: str | None = None):
        candidates = list(self.blobs.get(bucket_name, ()))
        if not prefix:
            return candidates
        return [blob for blob in candidates if blob.name.startswith(prefix)]


def test_format_paper_account_state_renders_zh_summary():
    state = PaperAccountState(
        paper_account_group="sg_coin_notify",
        cash=1250.0,
        nav=104500.0,
        positions={
            "CONL": {
                "quantity": 12.5,
                "average_cost": 34.2,
            }
        },
        metadata={
            "pending_plan": {"effective_date": "2026-04-23"},
            "last_run_as_of": "2026-04-22",
            "last_strategy_profile": "coin_short_hold_vt50",
        },
    )

    text = format_paper_account_state(state, lang="zh-CN")

    assert "账户组: sg_coin_notify" in text
    assert "净值: $104,500.00" in text
    assert "待执行生效日: 2026-04-23" in text
    assert "当前持仓" in text
    assert "- CONL: 数量=12.5000, 成本=$34.20" in text
    assert "- last_strategy_profile: coin_short_hold_vt50" in text


def test_load_latest_local_reconciliation_record_applies_filters(tmp_path):
    early_dir = tmp_path / "2026-04-21"
    late_dir = tmp_path / "2026-04-22"
    early_dir.mkdir()
    late_dir.mkdir()

    (early_dir / "global_etf_rotation__sg_alpha.json").write_text(
        json.dumps({"payload": {"as_of": "2026-04-21"}}),
        encoding="utf-8",
    )
    expected_path = late_dir / "global_etf_rotation__sg_alpha.json"
    expected_path.write_text(
        json.dumps({"payload": {"as_of": "2026-04-22"}}),
        encoding="utf-8",
    )
    (late_dir / "tqqq_growth_income__sg_alpha.json").write_text(
        json.dumps({"payload": {"as_of": "2026-04-22"}}),
        encoding="utf-8",
    )

    result = load_latest_local_reconciliation_record(
        str(tmp_path),
        strategy_profile="global_etf_rotation",
        paper_account_group="sg_alpha",
    )

    assert result is not None
    path, payload = result
    assert path == expected_path
    assert payload["payload"]["as_of"] == "2026-04-22"


def test_list_local_reconciliation_records_filters_by_date_profile_and_group(tmp_path):
    first_dir = tmp_path / "2026-04-20"
    second_dir = tmp_path / "2026-04-22"
    first_dir.mkdir()
    second_dir.mkdir()

    (first_dir / "global_etf_rotation__sg_alpha.json").write_text(
        json.dumps({"payload": {"as_of": "2026-04-20"}}),
        encoding="utf-8",
    )
    (second_dir / "global_etf_rotation__sg_alpha.json").write_text(
        json.dumps({"payload": {"as_of": "2026-04-22"}}),
        encoding="utf-8",
    )
    (second_dir / "global_etf_rotation__sg_beta.json").write_text(
        json.dumps({"payload": {"as_of": "2026-04-22"}}),
        encoding="utf-8",
    )

    records = list_local_reconciliation_records(
        str(tmp_path),
        strategy_profile="global_etf_rotation",
        paper_account_group="sg_alpha",
        start_date="2026-04-21",
        end_date="2026-04-22",
    )

    assert len(records) == 1
    assert records[0][0].name == "global_etf_rotation__sg_alpha.json"
    assert records[0][1]["payload"]["as_of"] == "2026-04-22"


def test_list_gcs_reconciliation_records_filters_by_date_profile_and_group():
    client = FakeListStorageClient(
        blobs={
            "paper-signal-artifacts": [
                FakeListBlob(
                    name="paper/2026-04-20/global_etf_rotation__sg_alpha.json",
                    payload={"payload": {"as_of": "2026-04-20"}},
                ),
                FakeListBlob(
                    name="paper/2026-04-22/global_etf_rotation__sg_alpha.json",
                    payload={"payload": {"as_of": "2026-04-22"}},
                ),
                FakeListBlob(
                    name="paper/2026-04-22/global_etf_rotation__sg_beta.json",
                    payload={"payload": {"as_of": "2026-04-22"}},
                ),
            ]
        }
    )

    records = list_gcs_reconciliation_records(
        bucket_name="paper-signal-artifacts",
        prefix="paper",
        strategy_profile="global_etf_rotation",
        paper_account_group="sg_alpha",
        start_date="2026-04-21",
        end_date="2026-04-22",
        storage_client=client,
    )

    assert len(records) == 1
    assert records[0][0] == "paper/2026-04-22/global_etf_rotation__sg_alpha.json"
    assert records[0][1]["payload"]["as_of"] == "2026-04-22"


def test_load_latest_gcs_reconciliation_record_returns_latest_match():
    client = FakeListStorageClient(
        blobs={
            "paper-signal-artifacts": [
                FakeListBlob(
                    name="paper/2026-04-21/tqqq_growth_income__sg_alpha.json",
                    payload={"payload": {"as_of": "2026-04-21"}},
                ),
                FakeListBlob(
                    name="paper/2026-04-22/tqqq_growth_income__sg_alpha.json",
                    payload={"payload": {"as_of": "2026-04-22"}},
                ),
            ]
        }
    )

    result = load_latest_gcs_reconciliation_record(
        bucket_name="paper-signal-artifacts",
        prefix="paper",
        strategy_profile="tqqq_growth_income",
        paper_account_group="sg_alpha",
        storage_client=client,
    )

    assert result is not None
    source, payload = result
    assert source == "paper/2026-04-22/tqqq_growth_income__sg_alpha.json"
    assert payload["payload"]["as_of"] == "2026-04-22"
