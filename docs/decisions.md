# FinTrace: Decision Log

Each entry records what was decided, why, and the evidence. Statuses: **Final**, **Provisional**
(revisit when stated), **Open**.

## Phase 0: Project rules

**R1. Baseline first.** Build a transaction-only model, then add graph features. One change per
experiment, so every gain can be attributed.

**R2. Temporal splits only.** Train, validation and test are separated by time. No random splits.

**R3. No future leakage.** Graph features use only data available before the prediction time.

**R4. Metrics.** PR-AUC, Precision@K, case-level recall, false-positive rate. Accuracy is not
used because the positive rate is about 0.1%.

**R5. The agent never declares guilt.** It organizes evidence for a human investigator. A
code-based verifier checks every cited transaction ID.

## Phase 1a: Data

**D1. Dataset: IBM AML HI-Small (Altman et al., NeurIPS 2023). Final.**
Chosen over AMLSim to avoid Java/WSL setup risk, and because it is a published benchmark.
The data is synthetic: injected patterns are easier to detect than real ones, so absolute
scores will not transfer to production. License: check the Kaggle page (believed to be
CDLA-Sharing-1.0) before redistributing any derived data.

**D2. Cases come from the patterns file. Final.**
370 cases (8 types, 40 to 54 each), parsed from `HI-Small_Patterns.txt`. The bridge table
`alert_transactions` links 3,209 transactions to cases. There are no hard negatives: every case
is a laundering attempt, so false positives come from normal accounts ranked high.

**D3. Unlinked positives. Final (cause unknown).**
1,968 of 5,177 positives (38%) belong to no case: 1,275 ACH and 693 Bitcoin, Cash, Cheque or
Credit Card. Only 42 touch an account that appears in a known case. We do not know why the
patterns file omits them. Transaction-level metrics are reported on all positives and on the
linked subset separately. Case-level recall uses the 370 cases only.

**D4. The tail is excluded from evaluation. Final.**
After 2022-09-10 normal volume collapses while laundering continues: 1,108 transactions, 59%
positive. The tail stays in the database but is never used for PR-AUC or Precision@K, and is
reported separately. No absolute-time feature (day or date) is allowed, because "late" would
predict laundering. Hour-of-day is allowed.

**D5. Node ID = (bank_id, account). Provisional until `check_node_ids` passes.**
8 account numbers appear under two different banks and entities, so the account number alone
would merge different accounts. Bank IDs are normalized by stripping leading zeros before
joining, because the transactions file uses `010` where the accounts file may use `10`.

**D6. Self-transfers. Final.**
591,212 rows (11.6%); 481,056 are Reinvestment with 0 positives. 11 ACH self-transfers are
positive. They are excluded from graph edges because they carry no flow between accounts and
would distort degree and cycle counts. They stay in `transactions` and are flagged with an
`is_self_transfer` feature. Those 11 positives get no graph evidence; this is stated in the
README.

**D7. Candidate split. Provisional (final in Phase 2).**
Train Sep 1 to 6, validation Sep 7 to 8, test Sep 9 to 10.

| Window | Transactions | Positives | Base rate |
|---|---|---|---|
| Train | 3,248,921 | 2,530 | 0.078% |
| Validation | 965,524 | 1,036 | 0.107% |
| Test | 862,792 | 956 | 0.111% |
| Tail | 1,108 | 655 | 59% |

Each case belongs to the split of its start time: 220 train, 64 validation, 79 test, and 7
tail-only cases excluded. Many cases straddle a boundary (for example, 59 of the 79 test cases
run into the tail). Case recall is reported as "x of y" with bootstrap intervals, because the
test set has few cases. Each split's base rate is always reported next to its PR-AUC.

**D8. Graph look-back windows. Provisional.**
Case duration has a median of 24 to 151 hours and a maximum of 202 hours (gather_scatter).
Windows of 24h, 72h and 7d will be tested in Phase 3.

**D9. Currencies. Open (decide in Phase 1b).**
15 currencies including Bitcoin. Raw amounts are not summed across currencies.

## Known dataset properties (for the README)

- ACH carries about 87% of all positives (about 4,483 of 5,177), and Wire and Reinvestment have
  none. A transaction-only baseline will already exploit this, so any graph gain must be judged
  against that baseline.
- Positive base rate varies by day (higher on weekends, when normal volume drops).

## Open items

- Phase 2: consider a gap between train and validation, because cases last up to 8 days.
- Phase 2: define "case caught" as at least one of its in-window transactions in the top K.
- Phase 1b: decide how to handle the 15 currencies.