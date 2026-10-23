"""Follow-up diagnostics for the FinTrace database (closes Phase 1a).

Run from the repo root:
    python -m src.data.diagnostics

The split dates are a CANDIDATE, used only to count positives and cases
per window. The final split is decided in Phase 2.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

DB = Path("data/processed/fintrace.duckdb")


def _window(col: str) -> str:
    """SQL CASE mapping a timestamp column to a candidate split window."""
    return f"""CASE
        WHEN CAST({col} AS DATE) <= DATE '2022-09-06' THEN '1_train'
        WHEN CAST({col} AS DATE) <= DATE '2022-09-08' THEN '2_val'
        WHEN CAST({col} AS DATE) <= DATE '2022-09-10' THEN '3_test'
        ELSE '4_tail'
    END"""


CHECKS: list[tuple[str, str]] = [
    (
        "A. Duplicate account_ids: identical rows or different banks/entities?",
        """
        SELECT * FROM accounts
        WHERE account_id IN (
            SELECT account_id FROM accounts GROUP BY 1 HAVING count(*) > 1
        )
        ORDER BY account_id
        """,
    ),
    (
        "B. Positives with and without a case, by payment format",
        """
        SELECT t.payment_format, (b.tx_id IS NOT NULL) AS in_case, count(*) AS n
        FROM transactions t
        LEFT JOIN (SELECT DISTINCT tx_id FROM alert_transactions) b USING (tx_id)
        WHERE t.is_laundering
        GROUP BY 1, 2 ORDER BY 1, 2
        """,
    ),
    (
        "C. Unlinked positives: do they touch accounts that are in known cases?",
        """
        WITH case_accounts AS (
            SELECT src_account AS account
            FROM transactions JOIN alert_transactions USING (tx_id)
            UNION
            SELECT dst_account
            FROM transactions JOIN alert_transactions USING (tx_id)
        ),
        unlinked AS (
            SELECT * FROM transactions
            WHERE is_laundering
              AND tx_id NOT IN (SELECT tx_id FROM alert_transactions)
        )
        SELECT count(*) AS n_unlinked,
               sum((src_account IN (SELECT account FROM case_accounts)
                    OR dst_account IN (SELECT account FROM case_accounts))::INT)
                   AS touching_a_case_account
        FROM unlinked
        """,
    ),
    (
        "D. Self-transfers by payment format",
        """
        SELECT payment_format, count(*) AS n, sum(is_laundering::INT) AS n_positive
        FROM transactions WHERE src_account = dst_account
        GROUP BY 1 ORDER BY 2 DESC
        """,
    ),
    (
        "E. Case duration by type (hours)",
        """
        SELECT alert_type, count(*) AS n_cases,
               median(date_diff('hour', start_time, end_time)) AS median_hours,
               max(date_diff('hour', start_time, end_time)) AS max_hours
        FROM alerts GROUP BY 1 ORDER BY 1
        """,
    ),
    (
        "F. Candidate windows: transactions, positives, base rate",
        f"""
        SELECT {_window('tx_time')} AS window_name,
               count(*) AS n_tx,
               sum(is_laundering::INT) AS n_positive,
               avg(is_laundering::INT) AS base_rate
        FROM transactions GROUP BY 1 ORDER BY 1
        """,
    ),
    (
        "G. Cases by start window vs end window (straddling cases)",
        f"""
        SELECT {_window('start_time')} AS start_window,
               {_window('end_time')} AS end_window,
               count(*) AS n_cases
        FROM alerts GROUP BY 1, 2 ORDER BY 1, 2
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