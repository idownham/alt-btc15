"""Merge tests on synthetic laptop/droplet DBs (docs/r1-droplet-move.md rules)."""

import sqlite3

import pytest

from slot.merge import NS, MergeError, merge
from slot.recorder import SCHEMA

T = 1_794_199_500  # a window boundary (multiple of 900)
W_BEFORE, W_CUT, W_AFTER = "KX-BEFORE", "KX-CUT", "KX-AFTER"


def make(path, host: str) -> None:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    wins = [(W_BEFORE, T - 900, T, "80000", "yes" if host == "laptop" else None, None, 1),
            (W_CUT, T, T + 900, "80100", None if host == "laptop" else "no", None, 2)]
    if host == "droplet":
        wins.append((W_AFTER, T + 900, T + 1800, "80200", "yes", None, 3))
    db.executemany("INSERT INTO windows VALUES (?,?,?,?,?,?,?)", wins)
    lo, hi = (T - 900, T + 900) if host == "laptop" else (T - 400, T + 1800)
    for s in range(lo, hi):
        ticker = W_BEFORE if s < T else W_CUT if s < T + 900 else W_AFTER
        db.execute("INSERT INTO books VALUES (?,?,?,?,?,?,?)", (ticker, s * NS, s * NS + 5, f"{4810 if host == 'laptop' else 4800}:100",
                                                                "5000:100", 1, 1))
        db.execute("INSERT INTO btc VALUES (?,?,?,?,?)", (s * NS + 7, "x", 8_000_000 + (host == "laptop"), 0, 0))
    trades = [("a1", W_BEFORE, "2026-11-09T04:31:00Z", 4800, 100, "no"),
              ("c1", W_CUT, "2026-11-09T04:46:00Z", 4800, 100, "no"),
              ("c2", W_CUT, "2026-11-09T04:47:00Z", 4900, 200, "yes")]
    if host == "droplet":
        trades.append(("z1", W_AFTER, "2026-11-09T05:01:00Z", 5000, 100, "yes"))
    db.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?)", trades)
    db.execute("INSERT INTO gaps VALUES (?,?,?)", ((T - 5000) * NS, (T - 4000) * NS, 1000.0) if host == "laptop"
               else ((T + 1000) * NS, (T + 1010) * NS, 10.0))
    db.execute("INSERT INTO events VALUES (?,?,?)", (T * NS, "start", host))
    db.commit()
    db.close()


@pytest.fixture
def dbs(tmp_path):
    lap, drop = tmp_path / "laptop.sqlite", tmp_path / "droplet.sqlite"
    make(lap, "laptop")
    make(drop, "droplet")
    return lap, drop, tmp_path / "merged.sqlite"


def test_books_and_btc_come_from_one_host_each_side_of_T(dbs):
    lap, drop, out = dbs
    rep = merge(lap, drop, out, T)
    db = sqlite3.connect(out)
    rows = db.execute("SELECT t_recv_ns, yes_bids FROM books").fetchall()
    assert all((y == "4810:100") == (t < T * NS) for t, y in rows)
    assert db.execute("SELECT COUNT(*) FROM books WHERE ticker = ?", (W_CUT,)).fetchone()[0] == 900
    assert {y for _, y in db.execute("SELECT t_recv_ns, yes_bids FROM books WHERE ticker = ?", (W_CUT,))} == {"4800:100"}
    btc = db.execute("SELECT t_recv_ns, price_c FROM btc").fetchall()
    assert all((p == 8_000_001) == (t < T * NS) for t, p in btc)
    assert len(btc) == 900 + 1800  # laptop T-900..T, droplet T..T+1800
    assert rep["books"]["laptop_dropped_from_T"] == 900 and rep["books"]["droplet_dropped_before_T"] == 400


def test_trades_union_deduplicated_and_overlap_checked(dbs):
    lap, drop, out = dbs
    rep = merge(lap, drop, out, T)
    db = sqlite3.connect(out)
    assert sorted(r[0] for r in db.execute("SELECT trade_id FROM trades")) == ["a1", "c1", "c2", "z1"]
    assert rep["trades"]["windows_on_both_tapes"][W_CUT] == {"both": 2, "laptop_only": 0, "droplet_only": 0,
                                                              "field_mismatch": 0}
    assert rep["trades"]["cutover_window_tapes_match"] is True


def test_overlap_tape_difference_is_reported(dbs):
    lap, drop, out = dbs
    d = sqlite3.connect(drop)
    d.execute("DELETE FROM trades WHERE trade_id = 'c2'")
    d.commit()
    d.close()
    rep = merge(lap, drop, out, T)
    assert rep["trades"]["windows_on_both_tapes"][W_CUT]["laptop_only"] == 1
    assert rep["trades"]["cutover_window_tapes_match"] is False


def test_same_trade_id_with_different_fields_fails(dbs):
    lap, drop, out = dbs
    d = sqlite3.connect(drop)
    d.execute("UPDATE trades SET count_e2 = 999 WHERE trade_id = 'c1'")
    d.commit()
    d.close()
    with pytest.raises(MergeError):
        merge(lap, drop, out, T)


def test_windows_union_fills_missing_results(dbs):
    lap, drop, out = dbs
    rep = merge(lap, drop, out, T)
    db = sqlite3.connect(out)
    res = dict(db.execute("SELECT ticker, result FROM windows"))
    assert res == {W_BEFORE: "yes", W_CUT: "no", W_AFTER: "yes"}
    assert rep["windows"]["results_filled_from_droplet"] == 1
    assert rep["windows"]["results_filled_from_laptop"] == 1


def test_conflicting_results_fail(dbs):
    lap, drop, out = dbs
    d = sqlite3.connect(drop)
    d.execute("UPDATE windows SET result = 'no' WHERE ticker = ?", (W_BEFORE,))
    d.commit()
    d.close()
    with pytest.raises(MergeError):
        merge(lap, drop, out, T)


def test_gaps_and_events_keep_their_host(dbs):
    lap, drop, out = dbs
    rep = merge(lap, drop, out, T)
    db = sqlite3.connect(out)
    assert sorted(db.execute("SELECT host, seconds FROM gaps")) == [("droplet", 10.0), ("laptop", 1000.0)]
    assert sorted(r[0] for r in db.execute("SELECT host FROM events")) == ["droplet", "laptop"]
    assert rep["gaps"]["laptop_ending_after_T"] == 0 and rep["gaps"]["droplet_starting_before_T"] == 0


def test_merged_db_works_with_the_maker_engine(dbs):
    from slot import maker
    lap, drop, out = dbs
    merge(lap, drop, out, T)
    db = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
    w = maker.load_window(db, db.execute("SELECT ticker, open_ts, close_ts, strike, result FROM windows "
                                         "WHERE ticker = ?", (W_CUT,)).fetchone())
    assert len(w.snaps) == 900 and w.yes_won is False
    gaps = db.execute("SELECT start_ns, end_ns FROM gaps").fetchall()
    assert len(gaps) == 2


def test_refuses_non_boundary_cutover_and_existing_output(dbs):
    lap, drop, out = dbs
    with pytest.raises(MergeError):
        merge(lap, drop, out, T + 1)
    out.write_text("")
    with pytest.raises(MergeError):
        merge(lap, drop, out, T)
