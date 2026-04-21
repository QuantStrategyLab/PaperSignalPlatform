from __future__ import annotations

from types import SimpleNamespace

from entrypoints.cloud_run import create_app


def test_healthz_returns_platform_id():
    app = create_app()
    client = app.test_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "platform_id": "paper_signal"}


def test_root_returns_scaffold_payload(monkeypatch):
    import entrypoints.cloud_run as cloud_run

    monkeypatch.setattr(
        cloud_run,
        "load_platform_runtime_settings",
        lambda project_id_resolver: SimpleNamespace(
            strategy_profile="global_etf_rotation",
            paper_account_group="sg_coin_notify",
            service_name="paper-signal-coin-sg",
        ),
    )
    monkeypatch.setattr(
        cloud_run,
        "load_strategy_runtime",
        lambda settings: SimpleNamespace(
            required_inputs=frozenset({"feature_snapshot"}),
            describe=lambda: {
                "strategy_profile": settings.strategy_profile,
                "paper_account_group": settings.paper_account_group,
                "service_name": settings.service_name,
                "mode": "paper_only",
            }
        ),
    )
    monkeypatch.setattr(
        cloud_run,
        "get_platform_profile_status_matrix",
        lambda: [{"profile": "global_etf_rotation"}],
    )
    app = create_app()
    client = app.test_client()

    response = client.post("/")

    assert response.status_code == 200
    assert response.get_json()["status"] == "scaffold_only"
    assert response.get_json()["runtime"]["mode"] == "paper_only"
    assert response.get_json()["profile_status_row_count"] == 1


def test_root_runs_cycle_for_market_history_profile(monkeypatch):
    import entrypoints.cloud_run as cloud_run

    monkeypatch.setattr(
        cloud_run,
        "load_platform_runtime_settings",
        lambda project_id_resolver: SimpleNamespace(
            strategy_profile="global_etf_rotation",
            paper_account_group="sg_coin_notify",
            service_name="paper-signal-coin-sg",
            market_data_provider="yfinance",
        ),
    )
    monkeypatch.setattr(
        cloud_run,
        "load_strategy_runtime",
        lambda settings: SimpleNamespace(
            required_inputs=frozenset({"market_history"}),
            describe=lambda: {
                "strategy_profile": settings.strategy_profile,
                "paper_account_group": settings.paper_account_group,
                "service_name": settings.service_name,
                "mode": "paper_only",
            },
        ),
    )
    monkeypatch.setattr(cloud_run, "build_runtime_dependencies", lambda settings: object())
    monkeypatch.setattr(cloud_run, "YFinanceDailyBarProvider", lambda: object())
    monkeypatch.setattr(
        cloud_run,
        "run_paper_signal_cycle",
        lambda settings, runtime, dependencies, market_data_provider: SimpleNamespace(
            status="ok",
            summary={"as_of": "2026-03-31", "queue_status": "queued_pending_plan"},
        ),
    )
    monkeypatch.setattr(
        cloud_run,
        "get_platform_profile_status_matrix",
        lambda: [{"profile": "global_etf_rotation"}],
    )
    app = create_app()
    client = app.test_client()

    response = client.post("/")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert response.get_json()["summary"]["queue_status"] == "queued_pending_plan"


def test_root_runs_cycle_for_derived_indicator_profile(monkeypatch):
    import entrypoints.cloud_run as cloud_run

    monkeypatch.setattr(
        cloud_run,
        "load_platform_runtime_settings",
        lambda project_id_resolver: SimpleNamespace(
            strategy_profile="soxl_soxx_trend_income",
            paper_account_group="sg_soxl_notify",
            service_name="paper-signal-soxl-sg",
            market_data_provider="yfinance",
        ),
    )
    monkeypatch.setattr(
        cloud_run,
        "load_strategy_runtime",
        lambda settings: SimpleNamespace(
            required_inputs=frozenset({"derived_indicators", "portfolio_snapshot"}),
            describe=lambda: {
                "strategy_profile": settings.strategy_profile,
                "paper_account_group": settings.paper_account_group,
                "service_name": settings.service_name,
                "mode": "paper_only",
            },
        ),
    )
    monkeypatch.setattr(cloud_run, "build_runtime_dependencies", lambda settings: object())
    monkeypatch.setattr(cloud_run, "YFinanceDailyBarProvider", lambda: object())
    monkeypatch.setattr(
        cloud_run,
        "run_paper_signal_cycle",
        lambda settings, runtime, dependencies, market_data_provider: SimpleNamespace(
            status="ok",
            summary={"as_of": "2026-04-08", "queue_status": "queued_pending_plan"},
        ),
    )
    monkeypatch.setattr(
        cloud_run,
        "get_platform_profile_status_matrix",
        lambda: [{"profile": "soxl_soxx_trend_income"}],
    )
    app = create_app()
    client = app.test_client()

    response = client.post("/")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert response.get_json()["summary"]["queue_status"] == "queued_pending_plan"
