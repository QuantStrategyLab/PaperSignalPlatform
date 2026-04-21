from __future__ import annotations

import os

from flask import Flask, jsonify

from application.market_data_service import YFinanceDailyBarProvider
from application.runtime_dependencies import build_runtime_dependencies
from application.signal_cycle import run_paper_signal_cycle
from strategy_registry import (
    PAPER_SIGNAL_PLATFORM,
    get_platform_profile_status_matrix,
)
from strategy_runtime import load_strategy_runtime
from runtime_config_support import load_platform_runtime_settings


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "platform_id": PAPER_SIGNAL_PLATFORM})

    @app.route("/", methods=["GET", "POST"])
    def run_once():
        settings = load_platform_runtime_settings(
            project_id_resolver=lambda: os.getenv("GOOGLE_CLOUD_PROJECT")
        )
        runtime = load_strategy_runtime(settings)
        if runtime.required_inputs not in {
            frozenset({"market_history"}),
            frozenset({"benchmark_history", "portfolio_snapshot"}),
            frozenset({"derived_indicators", "portfolio_snapshot"}),
        }:
            return jsonify(
                {
                    "status": "scaffold_only",
                    "platform_id": PAPER_SIGNAL_PLATFORM,
                    "runtime": runtime.describe(),
                    "profile_status_row_count": len(get_platform_profile_status_matrix()),
                    "notes": [
                        "broker_execution_disabled",
                        "shared_strategy_only",
                        "paper_cycle_not_wired_for_this_input_mode",
                    ],
                }
            )
        dependencies = build_runtime_dependencies(settings)
        if settings.market_data_provider != "yfinance":
            raise ValueError(
                f"Unsupported PAPER_SIGNAL_MARKET_DATA_PROVIDER={settings.market_data_provider!r}"
            )
        result = run_paper_signal_cycle(
            settings=settings,
            runtime=runtime,
            dependencies=dependencies,
            market_data_provider=YFinanceDailyBarProvider(),
        )
        return jsonify(
            {
                "status": result.status,
                "platform_id": PAPER_SIGNAL_PLATFORM,
                "runtime": runtime.describe(),
                "profile_status_row_count": len(get_platform_profile_status_matrix()),
                "summary": result.summary,
            }
        )

    return app
