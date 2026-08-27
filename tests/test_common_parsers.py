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
