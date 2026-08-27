import os
import time

from src.config import find_latest_db_path, resolve_db_path


def test_resolve_db_path_substitutes_run_id():
    assert resolve_db_path("data/market_{run_id}.db", "20260827T000000Z") == "data/market_20260827T000000Z.db"


def test_resolve_db_path_without_placeholder_is_unchanged():
    assert resolve_db_path("data/market.db", "20260827T000000Z") == "data/market.db"


def test_find_latest_db_path_picks_most_recently_modified(tmp_path):
    template = str(tmp_path / "market_{run_id}.db")
    older = tmp_path / "market_20260101T000000Z.db"
    newer = tmp_path / "market_20260827T000000Z.db"
    older.write_text("x")
    time.sleep(0.01)
    newer.write_text("x")
    assert find_latest_db_path(template) == str(newer)


def test_find_latest_db_path_none_when_no_runs_yet(tmp_path):
    template = str(tmp_path / "market_{run_id}.db")
    assert find_latest_db_path(template) is None


def test_find_latest_db_path_fixed_file_mode(tmp_path):
    fixed = tmp_path / "market.db"
    assert find_latest_db_path(str(fixed)) is None
    fixed.write_text("x")
    assert find_latest_db_path(str(fixed)) == str(fixed)


def test_different_runs_produce_different_files_end_to_end():
    run_a = resolve_db_path("data/market_{run_id}.db", "20260827T100000Z")
    run_b = resolve_db_path("data/market_{run_id}.db", "20260827T110000Z")
    assert run_a != run_b
