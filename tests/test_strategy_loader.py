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
    assert "tech_communication_pullback_enhancement" in SUPPORTED_STRATEGY_PROFILES
    assert "mega_cap_leader_rotation_top50_balanced" in SUPPORTED_STRATEGY_PROFILES


def test_removed_research_profiles_are_not_supported():
    for profile in (
        "dynamic_mega_leveraged_pullback",
        "mega_cap_leader_rotation_dynamic_top20",
        "mega_cap_leader_rotation_aggressive",
    ):
        with pytest.raises(ValueError):
            load_strategy_definition(profile)
        assert profile not in SUPPORTED_STRATEGY_PROFILES


def test_profile_status_matrix_does_not_expose_selection_role_fields():
    rows = get_platform_profile_status_matrix()
    assert all("is_default" not in row for row in rows)
    assert all("is_rollback" not in row for row in rows)


def test_profile_status_matrix_excludes_removed_research_profiles():
    rows = get_platform_profile_status_matrix()
    for profile in (
        "mega_cap_leader_rotation_dynamic_top20",
        "mega_cap_leader_rotation_aggressive",
        "dynamic_mega_leveraged_pullback",
    ):
        assert all(row["canonical_profile"] != profile for row in rows)
