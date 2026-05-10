from __future__ import annotations

from runtime_config_support import parse_paper_account_group_configs


def test_parse_paper_account_group_configs_supports_groups_wrapper():
    payload = """
    {
      "groups": {
        "sg_alpha": {
          "service_name": "paper-signal-alpha-sg",
          "account_alias": "sg-paper-alpha",
          "base_currency": "USD",
          "market_calendar": "XNYS",
          "starting_equity": 100000,
          "slippage_bps": 15,
          "commission_bps": 0,
          "fill_model": "next_open",
          "artifact_bucket_prefix": "paper-signal/sg/alpha"
        }
      }
    }
    """

    groups = parse_paper_account_group_configs(payload)

    group = groups["sg_alpha"]
    assert group.service_name == "paper-signal-alpha-sg"
    assert group.account_alias == "sg-paper-alpha"
    assert group.base_currency == "USD"
    assert group.market_calendar == "XNYS"
    assert group.starting_equity == 100000.0
    assert group.slippage_bps == 15.0
    assert group.commission_bps == 0.0
    assert group.fill_model == "next_open"
