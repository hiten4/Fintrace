"""Check that (bank_id, account_id) works as a node key. Read-only.

Run from the repo root:
    python -m src.data.check_node_ids
"""

from __future__ import annotations

from pathlib import Path

import duckdb

DB = Path("data/processed/fintrace.duckdb")


def bank(col: str) -> str:
    """SQL: strip leading zeros from a bank id ('00220' -> '220')."""
    return f"COALESCE(NULLIF(ltrim({col}, '0'), ''), '0')"


CHECKS: list[tuple[str, str]] = [
    (
        "1. Duplicate (bank, account) pairs in accounts (want 0)",
        f"""
        SELECT count(*) - count(DISTINCT {bank('bank_id')} || '|' || account_id) AS dup_pairs
        FROM accounts
        """,
    ),
    (
        "2. Transactions whose SOURCE (bank, account) is not in accounts (want 0)",
        f"""
        SELECT count(*) AS orphan_src FROM transactions t
        WHERE NOT EXISTS (
            SELECT 1 FROM accounts a
            WHERE a.account_id = t.src_account
              AND {bank('a.bank_id')} = {bank('t.from_bank')})
        """,
    ),
    (
        "3. Transactions whose DESTINATION (bank, account) is not in accounts (want 0)",
        f"""
        SELECT count(*) AS orphan_dst FROM transactions t
        WHERE NOT EXISTS (
            SELECT 1 FROM accounts a
            WHERE a.account_id = t.dst_account
              AND {bank('a.bank_id')} = {bank('t.to_bank')})
        """,
    ),
    (
        "4. Ambiguous account numbers as transaction source, by bank",
        """
        SELECT src_account AS account_id, from_bank, count(*) AS n_tx
        FROM transactions
        WHERE src_account IN (
            SELECT account_id FROM accounts GROUP BY 1 HAVING count(*) > 1)
        GROUP BY 1, 2 ORDER BY 1, 2
        """,
    ),
]


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    try:
        for title, sql in CHECKS:
            print(f"\n=== {title} ===")
            con.sql(sql).show()
    finally:
        con.close()


if __name__ == "__main__":
    main()