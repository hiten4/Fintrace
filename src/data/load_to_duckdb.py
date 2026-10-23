"""Load the IBM AML dataset (HI-Small) into DuckDB.

Run from the repo root:
    python -m src.data.load_to_duckdb

Tables:
    accounts            one row per account (from *_accounts.csv)
    transactions        one row per transaction, with is_laundering label
    alerts              one row per laundering attempt (case), parsed from *_Patterns.txt
    alert_transactions  bridge: which transactions belong to which alert

Design notes:
- The transactions CSV has two columns both named "Account", so we skip the
  header and assign our own column names (after checking the header is as expected).
- Everything is read as text, then cast explicitly, so types live in this file.
- Bank IDs stay VARCHAR because of leading zeros ("010" vs "10").
- Pattern lines are matched back to transactions on all 10 descriptive fields
  plus an occurrence number, so identical duplicate rows map one-to-one.
- The database is rebuilt from scratch on every run.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

SCHEMA: dict[str, list[tuple[str, str]]] = {
    "accounts": [
        ("account_id", "VARCHAR NOT NULL"),
        ("bank_id", "VARCHAR"),
        ("bank_name", "VARCHAR"),
        ("entity_id", "VARCHAR"),
        ("entity_name", "VARCHAR"),
    ],
    "transactions": [
        ("tx_id", "BIGINT NOT NULL"),
        ("tx_time", "TIMESTAMP NOT NULL"),
        ("from_bank", "VARCHAR"),
        ("src_account", "VARCHAR NOT NULL"),
        ("to_bank", "VARCHAR"),
        ("dst_account", "VARCHAR NOT NULL"),
        ("amount_received", "DOUBLE"),
        ("receiving_currency", "VARCHAR"),
        ("amount_paid", "DOUBLE"),
        ("payment_currency", "VARCHAR"),
        ("payment_format", "VARCHAR"),
        ("is_laundering", "BOOLEAN NOT NULL"),  # LABEL: never a feature
    ],
    "alerts": [
        ("alert_id", "BIGINT NOT NULL"),
        ("alert_type", "VARCHAR NOT NULL"),  # e.g. fan_out, cycle (from the file)
        ("description", "VARCHAR"),
        ("start_time", "TIMESTAMP"),
        ("end_time", "TIMESTAMP"),
        ("n_transactions", "INTEGER"),
    ],
    "alert_transactions": [
        ("alert_id", "BIGINT NOT NULL"),
        ("tx_id", "BIGINT NOT NULL"),
    ],
}
EXPECTED_COLUMNS: dict[str, list[str]] = {
    table: [name for name, _ in cols] for table, cols in SCHEMA.items()
}

TRANS_HEADER = [
    "Timestamp", "From Bank", "Account", "To Bank", "Account",
    "Amount Received", "Receiving Currency", "Amount Paid",
    "Payment Currency", "Payment Format", "Is Laundering",
]
TRANS_NAMES = [
    "ts", "from_bank", "src", "to_bank", "dst", "amount_received",
    "receiving_currency", "amount_paid", "payment_currency", "payment_format", "label",
]
ACCOUNTS_HEADER = ["Bank Name", "Bank ID", "Account Number", "Entity ID", "Entity Name"]
ACCOUNTS_NAMES = ["bank_name", "bank_id", "account_id", "entity_id", "entity_name"]

# The first 10 fields of a transaction line identify it (label excluded).
KEY_FIELDS = TRANS_NAMES[:10]
KEY_SQL = "concat_ws('|', " + ", ".join(KEY_FIELDS) + ")"

BEGIN_RE = re.compile(r"^BEGIN LAUNDERING ATTEMPT\s*-\s*([^:]+?)\s*(?::\s*(.*))?$")


# ---------- helpers ----------
def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _read_csv(path: Path, names: list[str]) -> str:
    names_sql = "[" + ", ".join(_sql_str(n) for n in names) + "]"
    return (
        f"read_csv({_sql_str(path.as_posix())}, header=false, skip=1, "
        f"names={names_sql}, all_varchar=true)"
    )


def _check_header(path: Path, expected: list[str]) -> None:
    with path.open(encoding="utf-8-sig") as f:
        first = f.readline().strip()
    if first.split(",") != expected:
        raise ValueError(
            f"{path.name}: unexpected header.\n  expected: {expected}\n  found:    {first}"
        )


def _count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def _normalize_type(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")


# ---------- patterns file parsing (pure Python, unit-testable) ----------
def parse_patterns(
    path: Path,
) -> tuple[list[tuple[int, str, str | None]], list[tuple]]:
    """Parse the patterns file.

    Returns:
        headers: (alert_id, alert_type, description), alert_id = order in file (1-based)
        rows:    (alert_id, line_no, <10 transaction fields as text>)
    """
    headers: list[tuple[int, str, str | None]] = []
    rows: list[tuple] = []
    current: int | None = None
    with path.open(encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            m = BEGIN_RE.match(line)
            if m:
                alert_id = len(headers) + 1
                headers.append((alert_id, _normalize_type(m.group(1)), m.group(2)))
                current = alert_id
                continue
            if line.startswith("END LAUNDERING ATTEMPT"):
                current = None
                continue
            fields = line.split(",")
            if current is None or len(fields) != 11:
                raise ValueError(f"{path.name} line {line_no}: cannot parse: {line!r}")
            rows.append((current, line_no, *fields[:10]))
    return headers, rows


# ---------- loaders ----------
def _load_accounts(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    _check_header(path, ACCOUNTS_HEADER)
    con.execute(
        f"""
        INSERT INTO accounts
        SELECT account_id, bank_id, bank_name, entity_id, entity_name
        FROM {_read_csv(path, ACCOUNTS_NAMES)}
        """
    )


def _load_transactions(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    _check_header(path, TRANS_HEADER)
    # tx_id: deterministic order. Timestamp strings (YYYY/MM/DD HH:MM) sort
    # chronologically. Fully identical rows are interchangeable.
    con.execute(
        f"""
        CREATE TEMP TABLE raw_tx AS
        SELECT row_number() OVER (
                   ORDER BY ts, src, dst, amount_paid, payment_format,
                            from_bank, to_bank, amount_received,
                            receiving_currency, payment_currency
               ) AS tx_id, *
        FROM {_read_csv(path, TRANS_NAMES)}
        """
    )
    con.execute(
        """
        INSERT INTO transactions
        SELECT tx_id,
               strptime(ts, '%Y/%m/%d %H:%M'),
               from_bank, src, to_bank, dst,
               TRY_CAST(amount_received AS DOUBLE), receiving_currency,
               TRY_CAST(amount_paid AS DOUBLE), payment_currency,
               payment_format,
               (label = '1')
        FROM raw_tx
        """
    )


def _load_alerts(con: duckdb.DuckDBPyConnection, patterns_path: Path) -> int:
    """Fill alerts and alert_transactions. Returns the number of unmatched pattern rows."""
    headers, rows = parse_patterns(patterns_path)

    con.execute(
        "CREATE TEMP TABLE alert_headers "
        "(alert_id BIGINT, alert_type VARCHAR, description VARCHAR)"
    )
    cols = ", ".join(f"{n} VARCHAR" for n in KEY_FIELDS)
    con.execute(f"CREATE TEMP TABLE pattern_rows (alert_id BIGINT, line_no INTEGER, {cols})")
    if headers:
        con.executemany("INSERT INTO alert_headers VALUES (?, ?, ?)", headers)
    if rows:
        marks = ", ".join(["?"] * (2 + len(KEY_FIELDS)))
        con.executemany(f"INSERT INTO pattern_rows VALUES ({marks})", rows)

    con.execute(
        f"""
        INSERT INTO alert_transactions
        WITH p AS (
            SELECT alert_id, {KEY_SQL} AS k,
                   row_number() OVER (PARTITION BY {KEY_SQL} ORDER BY line_no) AS occ
            FROM pattern_rows
        ),
        t AS (
            SELECT tx_id, {KEY_SQL} AS k,
                   row_number() OVER (PARTITION BY {KEY_SQL} ORDER BY tx_id) AS occ
            FROM raw_tx WHERE label = '1'
        )
        SELECT p.alert_id, t.tx_id FROM p JOIN t ON p.k = t.k AND p.occ = t.occ
        """
    )
    con.execute(
        """
        INSERT INTO alerts
        SELECT h.alert_id, h.alert_type, h.description,
               min(t.tx_time), max(t.tx_time), CAST(count(t.tx_id) AS INTEGER)
        FROM alert_headers h
        LEFT JOIN alert_transactions b ON b.alert_id = h.alert_id
        LEFT JOIN transactions t ON t.tx_id = b.tx_id
        GROUP BY h.alert_id, h.alert_type, h.description
        """
    )
    return len(rows) - _count(con, "alert_transactions")


# ---------- orchestration ----------
def build_database(
    raw_dir: Path,
    db_path: Path,
    prefix: str = "HI-Small",
) -> dict[str, int]:
    """Create the DuckDB file from the raw files. Returns row counts per table."""
    paths = {
        "accounts": raw_dir / f"{prefix}_accounts.csv",
        "transactions": raw_dir / f"{prefix}_Trans.csv",
        "patterns": raw_dir / f"{prefix}_Patterns.txt",
    }
    for name, p in paths.items():
        if not p.exists():
            found = sorted(x.name for x in raw_dir.glob("*")) if raw_dir.exists() else []
            raise FileNotFoundError(f"{name}: {p} not found. Files in {raw_dir}: {found}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    try:
        for table, cols in SCHEMA.items():
            ddl = ", ".join(f"{name} {typ}" for name, typ in cols)
            con.execute(f"CREATE TABLE {table} ({ddl})")

        _load_accounts(con, paths["accounts"])
        _load_transactions(con, paths["transactions"])
        unmatched = _load_alerts(con, paths["patterns"])

        counts = {t: _count(con, t) for t in SCHEMA}
        for table, n in counts.items():
            logger.info("Loaded %-20s %12d rows", table, n)
        n_pos = con.execute(
            "SELECT count(*) FROM transactions WHERE is_laundering"
        ).fetchone()[0]
        logger.info("Laundering transactions: %d", n_pos)
        if unmatched:
            logger.warning(
                "%d pattern rows could not be matched to a laundering transaction", unmatched
            )
        return counts
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--db", type=Path, default=Path("data/processed/fintrace.duckdb"))
    parser.add_argument("--prefix", default="HI-Small", help="File prefix, e.g. HI-Small")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_database(args.raw_dir, args.db, args.prefix)


if __name__ == "__main__":
    main()