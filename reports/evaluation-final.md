# PipeMind — evaluation results

Generated 2026-09-07 21:57 UTC by `scripts/evaluate_all.py` from the live database.


> Every number below is computed from rows in the running system. Where a metric cannot be computed, this report says so and states what is missing rather than estimating. The gaps are concentrated in one place — metrics that need human judgement as ground truth — and they are listed together at the end.



## Cost and latency

| provider | model | calls | total $ | mean ms | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| gemini | gemini-3.6-flash | 21 | 0.0271 | 6117 | 4652 | 14933 |
| gemini | gemini-2.0-flash | 14 | 0.0040 | 4491 | 4618 | 5817 |
| stub | stub-v1 | 1 | 0.0000 | 48 | 48 | 48 |

Mean cost per successful call: **$0.00087** over 36 calls.

Cache hit rate: **6%** (3/50). This rises with history — a cache hit requires the same failure signature to have been analysed before, so a young workspace cannot demonstrate the steady-state figure.


## Classification

Which arm decided the category, across all analyses:

| source | n |
|---|---|
| rules | 26 |
| ml | 4 |
| llm | 3 |
| hybrid | 3 |

Category distribution — note how uneven it is; a macro-F1 over this would be dominated by whichever classes happen to be populated:

| category | n |
|---|---|
| DATABASE | 16 |
| BUILD | 6 |
| TEST | 5 |
| DEPENDENCY | 3 |
| NETWORK | 2 |
| DOCKER | 2 |
| CONFIGURATION | 2 |

**Not measurable yet.** Macro-F1, per-class P/R/F1 and the confusion matrix need a labelled test set. The only source of labels is `analysis_feedback.correct_category`, written when a developer corrects PipeMind in the UI. **0 of 800 needed** (and >= 40 per category). Until then the rules classifier is unvalidated beyond the 7/7 agreement with the LLM recorded in `experiments/prompt-v1.md`.


## Confidence calibration

Stated confidence, bucketed. This is the *distribution* only — the second column of a calibration curve, 'actually correct', requires grading:

| bucket | n | mean stated confidence |
|---|---|---|
| 0.50–0.75 | 3 | 0.74 |
| 0.75–1.00 | 33 | 0.94 |

**Not measurable yet.** The headline result of roadmaps/23 — does 90% confidence mean right 90% of the time — needs 50 failures with a human-verified root cause, graded blind to the stated confidence. **0 graded so far.** Nothing in the schema records a grade, so this needs a grading pass and a column to hold the verdict.


## Retrieval

| quantity | value |
|---|---|
| failures recorded | 29 |
| distinct signatures | 9 |
| dedup ratio | 3.22× |
| failure embeddings | 10 |
| knowledge chunks | 5 |

The dedup ratio is the signature layer working: it is how many recorded failures collapse into one distinct problem. A ratio near 1.0 means either genuinely distinct failures or a normaliser that is leaking run-scoped values — `experiments/knowledge-retrieval.md` documents one such leak that made every repeat failure look new.

Threshold sensitivity was measured directly rather than inferred here; see `experiments/similarity-threshold.md` (failure-to-failure, 0.75 → 0.55) and `experiments/knowledge-retrieval.md` (knowledge chunks, 0.60 → 0.40, with the chunk-size and neighbour-expansion results).

**Not measurable yet.** Needs labelled similar/dissimilar failure pairs. None exist: the thresholds above were derived from measured score distributions on hand-built probe sets, not from a labelled retrieval benchmark.


## RAG contribution

RAG was used in **32/50** analyses (64%).

| used_rag | n | mean confidence | mean prompt tokens | mean $ |
|---|---|---|---|---|
| False | 4 | 0.82 | 2387 | 0.00029 |
| True | 32 | 0.93 | 1240 | 0.00094 |

**Confidence is not accuracy.** A difference in mean stated confidence between the two arms says the model felt more certain, not that it was more often right. The number that would justify the feature is root-cause accuracy with RAG on versus off, and that needs grading.

**Not measurable yet.** The same failures analysed with `use_rag` on and off, both graded. Requires the grading pass above plus a second paid run per failure.


## Anomaly detection

| status | n |
|---|---|
| resolved | 5 |
| open | 1 |

**Not measurable yet.** `anomalies.status = 'false_positive'` is the ground truth, and it is written only when a user pushes back on an alert in the UI. 6 anomalies recorded, **0 marked false positive** — which is an absence of feedback, not a precision of 100%. Reporting it as the latter would be the single most misleading number available.

The detector's own tuning is measured in `experiments/anomaly-v1.md`: a hardcoded 1.5× memory ratio produced 22 anomalies from 24 jobs, and MAD-based scoring reduced that to 3.


## End-to-end latency

**Not measurable yet.** Only 2 completed analyses with usable timestamps.


## Provider comparison

**Not measurable yet.** Requires Ollama running locally and 30 failures replayed through both. Not run: no local provider is configured on this machine. The offline path in roadmaps/23.5 depends on the same setup.


## What this evaluation cannot yet answer

Every blocked metric below shares one dependency: ground truth that only a human can produce. None of it is blocked on engineering.


| metric | what is needed |
|---|---|
| classification F1 | Macro-F1, per-class P/R/F1 and the confusion matrix need a labelled test set. The only source of labels is `analysis_feedback.correct_category`, written when a developer corrects PipeMind in the UI. **0 of 800 needed** (and >= 40 per category). Until then the rules classifier is unvalidated beyond the 7/7 agreement with the LLM recorded in `experiments/prompt-v1.md`. |
| calibration curve | The headline result of roadmaps/23 — does 90% confidence mean right 90% of the time — needs 50 failures with a human-verified root cause, graded blind to the stated confidence. **0 graded so far.** Nothing in the schema records a grade, so this needs a grading pass and a column to hold the verdict. |
| precision@k and MRR | Needs labelled similar/dissimilar failure pairs. None exist: the thresholds above were derived from measured score distributions on hand-built probe sets, not from a labelled retrieval benchmark. |
| RAG accuracy delta | The same failures analysed with `use_rag` on and off, both graded. Requires the grading pass above plus a second paid run per failure. |
| anomaly precision and false-positive rate | `anomalies.status = 'false_positive'` is the ground truth, and it is written only when a user pushes back on an alert in the UI. 6 anomalies recorded, **0 marked false positive** — which is an absence of feedback, not a precision of 100%. Reporting it as the latter would be the single most misleading number available. |
| end-to-end latency | Only 2 completed analyses with usable timestamps. |
| gemini vs local qwen2.5-coder | Requires Ollama running locally and 30 failures replayed through both. Not run: no local provider is configured on this machine. The offline path in roadmaps/23.5 depends on the same setup. |


The practical consequence is that PipeMind's *accuracy* is currently unvalidated, while its *cost, latency and behaviour* are measured. A report should say exactly that.
