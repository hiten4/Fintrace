# Decision Log

One entry per non-trivial choice. Be ready to defend each one in an interview.

## Template

### D-XXX: <short title>
- **Date:** YYYY-MM-DD
- **Phase:** N
- **Context:** What problem or question came up?
- **Options considered:** A, B, C
- **Decision:** What we chose
- **Why:** Reasoning, evidence, or numbers
- **Trade-offs / risks:** What we give up
- **How to revisit:** What result would change this decision?

---

## D-001: Temporal splits only
- **Date:** (fill in)
- **Phase:** 0
- **Context:** Transactions are time-ordered; a random split leaks the future into training.
- **Options considered:** Random split, group split by account, temporal split
- **Decision:** Temporal train/val/test split by time quantile (60/20/20)
- **Why:** Mirrors deployment, where we predict on data later than anything we trained on.
- **Trade-offs / risks:** Fewer positives per split; labels may be unevenly distributed over time.
- **How to revisit:** If a split has too few positives for stable metrics, adjust fractions, not the method.

## D-002: Baseline first, one change per experiment
- **Date:** (fill in)
- **Phase:** 0
- **Context:** Need to show that graph features add value beyond transaction features.
- **Decision:** Build a transaction-only LightGBM baseline, then add graph features in isolation.
- **Why:** Gives a clean ablation. Any gain is attributable to the one thing changed.
- **Trade-offs / risks:** Slower than adding everything at once.

## D-003: AMLSim as dataset
- **Date:** (fill in)
- **Phase:** 0
- **Context:** Real AML data is not public.
- **Decision:** Use AMLSim (synthetic) and state the limitation prominently in the README.
- **Why:** Contains labeled laundering patterns and account relationships.
- **Trade-offs / risks:** Patterns follow generator rules, so performance will be optimistic and may not transfer.