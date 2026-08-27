from src.models import taker_side


def test_taker_side_buyer_is_maker_means_taker_sold():
    assert taker_side(True) == "SELL"


def test_taker_side_buyer_is_taker_means_taker_bought():
    assert taker_side(False) == "BUY"
