from __future__ import annotations

import json

from signal_notifier.signal_notifier_core import (
    build_notification_identity,
    read_json_snapshot,
    should_send_notification,
    write_json_snapshot,
)


def test_write_and_read_json_snapshot_round_trip(tmp_path):
    snapshot = {
        "as_of": "2026-04-23",
        "side": "cash",
        "gross_exposure": 0.0,
        "ready": True,
    }

    target_path = tmp_path / "snapshot.json"
    output_path = write_json_snapshot(snapshot, target_path)

    assert output_path == str(target_path.resolve())
    assert json.loads(target_path.read_text(encoding="utf-8")) == snapshot
    assert read_json_snapshot(target_path) == snapshot


def test_should_send_notification_uses_default_identity_fields():
    first = {
        "as_of": "2026-04-23",
        "ready": True,
        "side": "long",
        "target_symbol": "CONL",
        "gross_exposure": 0.42,
    }
    second = dict(first)
    third = dict(first, gross_exposure=0.41)

    assert should_send_notification(first, second) is False
    assert should_send_notification(third, second) is True


def test_build_notification_identity_supports_extra_keys():
    snapshot = {
        "as_of": "2026-04-23",
        "ready": True,
        "side": "cash",
        "target_symbol": None,
        "gross_exposure": 0.0,
    }

    identity = build_notification_identity(snapshot, extra_keys={"reason": "no_trend_signal"})

    assert identity["as_of"] == "2026-04-23"
    assert identity["reason"] == "no_trend_signal"
