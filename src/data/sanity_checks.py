"""Print sanity checks for the loaded FinTrace database.

Run from the repo root:
    python -m src.data.sanity_checks
"""

from __future__ import annotations

from pathlib import Path

import duckdb

DB = Path("data/processed/fintrace.duckdb")

CHECKS: list[tuple[str, str]] = [
    (
        "1. Row counts",
        """
        SELECT (SELECT count(*) FROM accounts) AS accounts,
               (SELECT count(*) FROM transactions) AS transactions,
               (SELECT count(*) FROM alerts) AS alerts,
               (SELECT count(*) FROM alert_transactions) AS bridge_rows
        """,
    ),
    (
        "2. Time range",
        "SELECT min(tx_time) AS first_tx, max(tx_time) AS last_tx FROM transactions",
    ),
    (
        "3. Transactions and positives per day",
        """
        SELECT CAST(tx_time AS DATE) AS day, count(*) AS n_tx,
               sum(is_laundering::INT) AS n_positive
        FROM transactions GROUP BY 1 ORDER BY 1
        """,
    ),
    (
        "4. Laundering share",
        """
        SELECT sum(is_laundering::INT) AS n_positive,
               avg(is_laundering::INT) AS laundering_share
        FROM transactions
        """,
    ),
    (
        "5. Alert mix",
        """
        SELECT alert_type, count(*) AS n_alerts, avg(n_transactions) AS avg_txs
        FROM alerts GROUP BY 1 ORDER BY 2 DESC
        """,
    ),
    (
        "6. Labels vs alerts consistency",
        """
        SELECT t.is_laundering, (b.tx_id IS NOT NULL) AS in_alert, count(*) AS n
        FROM transactions t
        LEFT JOIN (SELECT DISTINCT tx_id FROM alert_transactions) b USING (tx_id)
        GROUP BY 1, 2 ORDER BY 1, 2
        """,
    ),
    (
        "7a. Duplicate accounts",
        "SELECT count(*) - count(DISTINCT account_id) AS duplicate_accounts FROM accounts",
    ),
    (
        "7b. Orphan transactions (account missing from accounts table)",
        """
        SELECT count(*) AS orphan_txs FROM transactions
        WHERE src_account NOT IN (SELECT account_id FROM accounts)
           OR dst_account NOT IN (SELECT account_id FROM accounts)
        """,
    ),
    (
        "7c. Self-transfers and bad amounts",
        """
        SELECT sum((src_account = dst_account)::INT) AS self_transfers,
               sum((amount_paid IS NULL OR amount_paid <= 0)::INT) AS bad_amounts
        FROM transactions
        """,
    ),
    (
        "8a. Currencies",
        """
        SELECT payment_currency, count(*) AS n
        FROM transactions GROUP BY 1 ORDER BY 2 DESC
        """,
    ),
    (
        "8b. Payment formats",
        """
        SELECT payment_format, count(*) AS n,
               avg(is_laundering::INT) AS laundering_share
        FROM transactions GROUP BY 1 ORDER BY 2 DESC
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