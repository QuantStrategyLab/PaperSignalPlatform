from __future__ import annotations

import pytest

from us_equity_strategies import get_runtime_enabled_profiles

from strategy_loader import load_strategy_definition
from strategy_registry import (
    PAPER_SIGNAL_PLATFORM,
    PAPER_SIGNAL_RUNTIME_READY_OVERRIDES,
    SUPPORTED_STRATEGY_PROFILES,
    get_platform_profile_status_matrix,
    get_supported_profiles_for_platform,
)


def test_load_strategy_definition_requires_explicit_profile():
    with pytest.raises(EnvironmentError):
        load_strategy_definition(None)


def test_supported_profiles_matches_policy_accessor():
    assert get_supported_profiles_for_platform(PAPER_SIGNAL_PLATFORM) == SUPPORTED_STRATEGY_PROFILES


def test_supported_profiles_include_shared_runtime_enabled_profiles():
    assert "global_etf_rotation" in SUPPORTED_STRATEGY_PROFILES
    assert "tqqq_growth_income" in SUPPORTED_STRATEGY_PROFILES
    assert "soxl_soxx_trend_income" in SUPPORTED_STRATEGY_PROFILES
    assert "tech_communication_pullback_enhancement" in SUPPORTED_STRATEGY_PROFILES
    assert "mega_cap_leader_rotation_top50_balanced" in SUPPORTED_STRATEGY_PROFILES


def test_supported_profiles_include_paper_only_runtime_ready_override():
    assert "dynamic_mega_leveraged_pullback" in PAPER_SIGNAL_RUNTIME_READY_OVERRIDES
    assert "dynamic_mega_leveraged_pullback" in SUPPORTED_STRATEGY_PROFILES
    definition = load_strategy_definition("dynamic_mega_leveraged_pullback")
    assert definition.profile == "dynamic_mega_leveraged_pullback"


def test_profile_status_matrix_does_not_expose_selection_role_fields():
    rows = get_platform_profile_status_matrix()
    assert all("is_default" not in row for row in rows)
    assert all("is_rollback" not in row for row in rows)


def test_profile_status_matrix_marks_dynamic_mega_enabled_for_paper_signal_only():
    rows = get_platform_profile_status_matrix()
    dynamic_row = next(
        row for row in rows if row["canonical_profile"] == "dynamic_mega_leveraged_pullback"
    )
    assert dynamic_row["eligible"] is True
    assert dynamic_row["enabled"] is True
    assert "dynamic_mega_leveraged_pullback" not in get_runtime_enabled_profiles()
