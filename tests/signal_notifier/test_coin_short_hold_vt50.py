from __future__ import annotations

import pandas as pd

from signal_notifier.coin_short_hold_vt50 import CoinShortHoldVT50Config, compute_coin_short_hold_vt50_signal


def _business_index():
    return pd.date_range("2025-01-01", periods=260, freq="B")


def test_coin_short_hold_vt50_defaults_to_fixed_50_and_btc_ma150_filter():
    config = CoinShortHoldVT50Config()

    assert config.position_sizing == "fixed"
    assert config.fixed_weight == 0.50
    assert config.btc_ma == 150


def test_compute_coin_short_hold_vt50_signal_prefers_conl_in_uptrend():
    index = _business_index()
    coin_values = [100.0] * 240 + [102.0, 104.0, 107.0, 111.0, 116.0, 122.0, 128.0, 133.0, 138.0, 142.0, 146.0, 150.0, 153.0, 156.0, 160.0, 164.0, 168.0, 171.0, 174.0, 178.0]
    btc_values = [80.0 + 0.4 * i for i in range(len(index))]
    coin_close = pd.Series(coin_values, index=index)
    btc_close = pd.Series(btc_values, index=index)

    signal = compute_coin_short_hold_vt50_signal(coin_close, btc_close, as_of=index[-1])

    assert signal.ready is True
    assert signal.side == "long"
    assert signal.target_symbol == "CONL"
    assert signal.diagnostics["strategy_config"]["btc_ma"] == 150
    assert signal.target_weights["CONL"] == 0.50


def test_compute_coin_short_hold_vt50_signal_prefers_coni_in_downtrend():
    index = _business_index()
    coin_values = [220.0] * 240 + [216.0, 211.0, 205.0, 198.0, 190.0, 182.0, 175.0, 169.0, 164.0, 160.0, 157.0, 154.0, 150.0, 147.0, 144.0, 141.0, 138.0, 136.0, 134.0, 132.0]
    btc_values = [220.0 - 0.5 * i for i in range(len(index))]
    coin_close = pd.Series(coin_values, index=index)
    btc_close = pd.Series(btc_values, index=index)

    signal = compute_coin_short_hold_vt50_signal(coin_close, btc_close, as_of=index[-1])

    assert signal.ready is True
    assert signal.side == "short"
    assert signal.target_symbol == "CONI"
    assert signal.target_weights["CONI"] == 0.50


def test_coin_short_hold_vt50_execution_payload_uses_weight_allocation():
    index = _business_index()
    coin_values = [100.0] * 240 + [102.0, 104.0, 107.0, 111.0, 116.0, 122.0, 128.0, 133.0, 138.0, 142.0, 146.0, 150.0, 153.0, 156.0, 160.0, 164.0, 168.0, 171.0, 174.0, 178.0]
    btc_values = [80.0 + 0.4 * i for i in range(len(index))]
    coin_close = pd.Series(coin_values, index=index)
    btc_close = pd.Series(btc_values, index=index)

    signal = compute_coin_short_hold_vt50_signal(coin_close, btc_close, as_of=index[-1])
    target_weights, metadata = signal.to_execution_payload()

    assert target_weights == signal.target_weights
    assert metadata["allocation"]["target_mode"] == "weight"
    assert metadata["allocation"]["targets"] == signal.target_weights
    assert tuple(metadata["managed_symbols"]) == ("CONL", "CONI")
