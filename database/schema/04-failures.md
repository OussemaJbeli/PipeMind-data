# Group 4 — Failure & Intelligence

`failure_signatures` · `failures` · `analyses` · `analysis_evidence` · `recommendations` · `analysis_feedback`

## Purpose

Turning a failed job into an explained failure with evidence, and learning from the result.

## `failure_signatures` — the load-bearing table

One row per distinct *normalised* error, per team. The error text has numbers, paths,
UUIDs, timestamps and hex stripped to placeholders, then hashed with the ecosystem.

That single `hash` column gives four things at once:

1. **Deduplication** — the same bug is one row, not forty
2. **Clustering** — `occurrence_count` shows what actually keeps breaking
3. **LLM cache key** — the same signature returns a cached analysis at zero cost
4. **Similarity join** — links a new failure to its history

**Tuning:** if `occurrence_count` is always 1 you are under-normalising. If distinct bugs
share a signature you are over-normalising. Check with:

```sql
SELECT occurrence_count, count(*) FROM failure_signatures GROUP BY 1 ORDER BY 1;
```

A healthy distribution is a long tail of 1s with a meaningful head of repeat offenders.

**`is_known` + `known_resolution`** enable the deterministic short-circuit: a confirmed
signature with a confident classifier needs no model call at all. Track how often this
fires — it is the clearest evidence that historical intelligence works.

## `analyses` — provenance matters as much as the conclusion

`classification_source` (`rules` | `ml` | `llm` | `hybrid`) answers, with data, *"how
often did we actually need the LLM?"* If the answer is 8%, the cheap layers are carrying
the system. That number belongs in the report.

`confidence` is calibrated, not the model's raw self-report: corroboration from the rule
engine and from history adjusts it, because those are signals the model does not get to
grade itself on.

`cost_usd`, `latency_ms` and `cache_hit` are recorded on every analysis — including cache
hits at zero cost, which is the row that proves caching works.

## `analysis_evidence` — what makes the AI trustworthy

Every claim points at something real via `source_ref`: `job_logs#L1294`, a file path, or
`failure:<uuid>`. The UI renders each item as a link. An unverifiable claim is not
evidence, and this table is what stops the analysis panel being a wall of assertions.

## `analysis_feedback` — free training data

`correct_category` is a human-verified label, perfectly in-domain, contributed by a
developer who just debugged the failure. Export it as ground truth (roadmaps/08). This is
the mechanism that improves the classifier without manual labelling sessions.

## Gotchas

- `failures.category` is written twice: once at ingest by the classifier (which sees only
  the error block) and again by the analysis (which saw full context). The analysis wins.
- `severity` is a deterministic rule, not an AI decision — it must be stable and
  explainable before any model has run.
- Flaky failures are detected before analysis and skipped. Analysing the same flake twenty
  times is the fastest way to exhaust a budget for zero insight.
