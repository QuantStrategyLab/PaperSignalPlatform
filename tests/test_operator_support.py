from __future__ import annotations

import json

from application.operator_support import (
    format_paper_account_state,
    load_latest_local_reconciliation_record,
)
from application.state_store_service import PaperAccountState


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
