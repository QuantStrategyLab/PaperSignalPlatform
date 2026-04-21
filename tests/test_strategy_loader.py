from __future__ import annotations

import pytest

from strategy_loader import load_strategy_definition
from strategy_registry import (
    PAPER_SIGNAL_PLATFORM,
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


def test_profile_status_matrix_does_not_expose_selection_role_fields():
    rows = get_platform_profile_status_matrix()
    assert all("is_default" not in row for row in rows)
    assert all("is_rollback" not in row for row in rows)
