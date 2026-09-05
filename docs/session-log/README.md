# Session log (archive)

Point-in-time reports from the 2026-09-06 session. **Superseded as status by
`MASTER_SUMMARY.md` at the repo root** - read that first.

These are kept rather than deleted because each holds something the summary does not.
If you are looking for one specific thing, this is where it lives:

| File | Read it for |
|---|---|
| `GAP_REPORT.md` | **Per-claim line-number citations**, and the audit of teammate commit `c50cab9` done by checking that commit out separately. The most thorough document here. |
| `TEAM_SUMMARY.md` | **Git attribution** - who wrote which commits - plus a merge risk map and suggested merge order. |
| `STATUS_UPDATE.md` | What Features 1-3 (chatbot, benchmarking, invoice matching) **assume about the 22-key field vocabulary**. Matters most if `domain.ts` on `origin/main` moved that vocabulary. |
| `WIRING_STATUS.md` | Fix 1 / Fix 2 evidence, and **step-by-step instructions for demoing the real pipeline path**. |
| `AUDIT_REPORT.md` | The original six-must-have scorecard and the "what would have to exist to flip this score" analysis. |
| `CONSOLIDATION_PLAN.md` | Why these files ended up here, and the full inventory of every markdown file in the repo. |

Where a claim here disagrees with `MASTER_SUMMARY.md`, the summary is newer and wins.
Two known cases: the earlier reports quote a lower test count (they predate later work, and
one figure was measured with the wrong Python interpreter), and they describe the
real-conflict `fieldIds` problem before its root cause - a field-vocabulary gap - was found.
