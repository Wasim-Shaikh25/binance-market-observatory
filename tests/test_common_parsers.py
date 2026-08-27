from src.connectors import common


def test_parse_trade_computes_quote_quantity_exactly():
    data = {"t": 123, "E": 1000, "T": 999, "p": "10000.10000000", "q": "0.00100000", "m": True}
    parsed = common.parse_trade(data)
    assert parsed["trade_id"] == 123
    assert parsed["price"] == "10000.10000000"
    assert parsed["quantity"] == "0.00100000"
    # Decimal multiplication must be exact, not float-rounded.
    assert parsed["quote_quantity"] == "10.0001000000000000"
    assert parsed["buyer_maker"] is True


def test_parse_symbol_info_extracts_filters_and_margin_flag():
    sym = {
        "status": "TRADING",
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "isMarginTradingAllowed": True,
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
            {"filterType": "LOT_SIZE", "stepSize": "0.00000100", "minQty": "0.00001000"},
            {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
        ],
    }
    parsed = common.parse_symbol_info(sym)
    assert parsed["tick_size"] == "0.01000000"
    assert parsed["step_size"] == "0.00000100"
    assert parsed["min_qty"] == "0.00001000"
    assert parsed["min_notional"] == "5.00000000"
    assert parsed["margin_tradable"] is True


def test_parse_symbol_info_omits_margin_flag_for_futures():
    sym = {"status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT", "contractType": "PERPETUAL", "filters": []}
    parsed = common.parse_symbol_info(sym)
    assert "margin_tradable" not in parsed
    assert parsed["contract_type"] == "PERPETUAL"


def test_funding_from_mark_price_reuses_stream_fields():
    mp = common.parse_mark_price({"p": "50000.00", "i": "49999.00", "r": "0.0001", "T": 1700000000000})
    funding = common.funding_from_mark_price(mp)
    assert funding == {"funding_rate": "0.0001", "funding_time": 1700000000000, "mark_price": "50000.00"}


def test_funding_from_mark_price_none_when_fields_missing():
    mp = common.parse_mark_price({"p": "50000.00"})
    assert common.funding_from_mark_price(mp) is None


def test_parse_force_order_extracts_side_and_price():
    data = {"E": 1700000000000, "o": {"s": "BTCUSDT", "S": "SELL", "o": "LIMIT", "p": "49000.00", "ap": "48990.00", "q": "1.000", "X": "FILLED"}}
    parsed = common.parse_force_order(data)
    assert parsed["side"] == "SELL"
    assert parsed["price"] == "49000.00"
    assert parsed["order_status"] == "FILLED"


def test_parse_agg_trade_captures_event_time():
    data = {"a": 1, "p": "1", "q": "1", "T": 100, "E": 101, "m": False}
    assert common.parse_agg_trade(data)["event_time"] == 101


def test_parse_ticker_24h_captures_event_time():
    data = {"E": 123, "O": 100, "C": 200}
    parsed = common.parse_ticker_24h(data)
    assert parsed["event_time"] == 123
    assert parsed["open_time"] == 100
    assert parsed["close_time"] == 200


def test_parse_mark_price_captures_event_time():
    parsed = common.parse_mark_price({"p": "50000", "E": 999})
    assert parsed["event_time"] == 999


def test_parse_depth_snapshot_captures_futures_timestamps_when_present():
    # Spot's REST depth snapshot has no E/T fields at all.
    spot = common.parse_depth_snapshot({"lastUpdateId": 1, "bids": [], "asks": []})
    assert spot["event_time"] is None
    assert spot["transaction_time"] is None

    # Futures' REST depth snapshot does carry them.
    futures = common.parse_depth_snapshot({"lastUpdateId": 1, "bids": [], "asks": [], "E": 111, "T": 222})
    assert futures["event_time"] == 111
    assert futures["transaction_time"] == 222


def test_parse_open_interest_captures_source_time_distinct_from_receive_time():
    parsed = common.parse_open_interest({"openInterest": "12345.6", "symbol": "BTCUSDT", "time": 1700000000000})
    assert parsed == {"open_interest": "12345.6", "observation_time": 1700000000000}


def test_parse_positioning_entry_picks_the_right_value_field_per_metric():
    entry = {"symbol": "BTCUSDT", "longShortRatio": "1.43", "longAccount": "0.59", "shortAccount": "0.41", "timestamp": 1700000000000}
    parsed = common.parse_positioning_entry("globalLongShortAccountRatio", entry)
    assert parsed == {"value": "1.43", "observation_time": 1700000000000}


def test_parse_positioning_entry_taker_ratio_uses_buy_sell_ratio_field():
    entry = {"buySellRatio": "1.51", "buyVol": "100", "sellVol": "66", "timestamp": 1700000000000}
    parsed = common.parse_positioning_entry("takerlongshortRatio", entry)
    assert parsed["value"] == "1.51"


def test_parse_positioning_entry_unknown_metric_has_no_value():
    parsed = common.parse_positioning_entry("somethingNew", {"timestamp": 1})
    assert parsed["value"] is None
    assert parsed["observation_time"] == 1
