from pathlib import Path

import duckdb
import pytest

from src.data.load_to_duckdb import EXPECTED_COLUMNS, build_database

REAL_DB = Path("data/processed/fintrace.duckdb")

TRANS = """Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering
2022/09/01 00:20,010,A1,010,A1,100.00,US Dollar,100.00,US Dollar,Reinvestment,0
2022/09/01 00:06,021,A2,012,A3,50.00,Euro,50.00,Euro,ACH,1
2022/09/01 04:33,021,A2,020,A4,60.00,Euro,60.00,Euro,ACH,1
2022/09/02 10:00,012,A3,021,A2,50.00,Euro,50.00,Euro,ACH,1
2022/09/02 10:00,012,A3,021,A2,50.00,Euro,50.00,Euro,ACH,1
2022/09/03 09:00,020,A4,010,A1,5.00,US Dollar,5.00,US Dollar,Cheque,0
"""

ACCOUNTS = """Bank Name,Bank ID,Account Number,Entity ID,Entity Name
Bank #1,10,A1,E1,Corporation #1
Bank #2,21,A2,E2,Corporation #2
Bank #3,12,A3,E3,Sole Proprietorship #3
Bank #4,20,A4,E4,Corporation #4
"""

PATTERNS = """BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out
2022/09/01 00:06,021,A2,012,A3,50.00,Euro,50.00,Euro,ACH,1
2022/09/01 04:33,021,A2,020,A4,60.00,Euro,60.00,Euro,ACH,1
END LAUNDERING ATTEMPT - FAN-OUT

BEGIN LAUNDERING ATTEMPT - SCATTER-GATHER:  Max 1-degree
2022/09/02 10:00,012,A3,021,A2,50.00,Euro,50.00,Euro,ACH,1
END LAUNDERING ATTEMPT - SCATTER-GATHER

BEGIN LAUNDERING ATTEMPT - CYCLE
2022/09/02 10:00,012,A3,021,A2,50.00,Euro,50.00,Euro,ACH,1
END LAUNDERING ATTEMPT - CYCLE
"""


def _columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    return [r[0] for r in rows]


def _write_raw(raw: Path, trans: str = TRANS) -> None:
    raw.mkdir(exist_ok=True)
    (raw / "HI-Small_Trans.csv").write_text(trans)
    (raw / "HI-Small_accounts.csv").write_text(ACCOUNTS)
    (raw / "HI-Small_Patterns.txt").write_text(PATTERNS)


@pytest.fixture()
def tiny_db(tmp_path: Path) -> Path:
    _write_raw(tmp_path / "raw")
    db = tmp_path / "test.duckdb"
    build_database(tmp_path / "raw", db)
    return db


def test_tables_and_columns_exist(tiny_db: Path) -> None:
    con = duckdb.connect(str(tiny_db), read_only=True)
    for table, expected in EXPECTED_COLUMNS.items():
        assert _columns(con, table) == expected
    con.close()


def test_row_counts_and_labels(tiny_db: Path) -> None:
    con = duckdb.connect(str(tiny_db), read_only=True)
    assert con.execute("SELECT count(*) FROM accounts").fetchone()[0] == 4
    assert con.execute("SELECT count(*) FROM transactions").fetchone()[0] == 6
    assert con.execute("SELECT count(*) FROM transactions WHERE is_laundering").fetchone()[0] == 4
    # leading zeros preserved
    assert con.execute(
        "SELECT count(*) FROM transactions WHERE from_bank = '010'"
    ).fetchone()[0] == 1
    # tx_id is unique and 1..n
    assert con.execute("SELECT count(DISTINCT tx_id), max(tx_id) FROM transactions").fetchone() == (6, 6)
    con.close()


def test_alerts_parsed_and_linked(tiny_db: Path) -> None:
    con = duckdb.connect(str(tiny_db), read_only=True)
    types = [r[0] for r in con.execute("SELECT alert_type FROM alerts ORDER BY alert_id").fetchall()]
    assert types == ["fan_out", "scatter_gather", "cycle"]
    sizes = [r[0] for r in con.execute("SELECT n_transactions FROM alerts ORDER BY alert_id").fetchall()]
    assert sizes == [2, 1, 1]
    # the two identical duplicate transactions map to different alerts, one-to-one
    assert con.execute("SELECT count(*), count(DISTINCT tx_id) FROM alert_transactions").fetchone() == (4, 4)
    start = con.execute("SELECT start_time FROM alerts WHERE alert_id = 1").fetchone()[0]
    assert str(start).startswith("2022-09-01 00:06")
    con.close()


def test_bad_header_raises(tmp_path: Path) -> None:
    _write_raw(tmp_path / "raw", trans=TRANS.replace("Is Laundering", "Label"))
    with pytest.raises(ValueError, match="unexpected header"):
        build_database(tmp_path / "raw", tmp_path / "bad.duckdb")


@pytest.mark.skipif(not REAL_DB.exists(), reason="real database not built yet")
def test_real_database_schema() -> None:
    con = duckdb.connect(str(REAL_DB), read_only=True)
    for table, expected in EXPECTED_COLUMNS.items():
        assert _columns(con, table) == expected
        assert con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0
    con.close()