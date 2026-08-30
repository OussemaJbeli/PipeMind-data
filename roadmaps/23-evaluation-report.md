# 23 — Evaluation, Report & Demo

**Repo:** `PipeMind-data` · **Depends on:** 22 · **Milestone:** ship

Measure what you built, write the report from what actually happened, and prepare a demo that cannot fail.

---

## 23.1 The evaluation run

One script, one output, reproducible.

```python
# spec — PipeMind-data/scripts/evaluate_all.py
# Produces PipeMind-data/reports/evaluation-final.md from live data.
#
# 1. CLASSIFICATION      held-out test set from file 08
#    macro-F1, weighted-F1, per-class P/R/F1, confusion matrix
#    four arms: rules · ml · hybrid · llm-only
#
# 2. ROOT CAUSE          50 failures with a human-verified cause
#    correct / partially correct / wrong  (you grade them, blind to confidence)
#    accuracy by confidence bucket → the calibration curve
#
# 3. RETRIEVAL           labeled similar/dissimilar pairs
#    precision@1, @3, @5 · MRR · threshold sensitivity
#
# 4. RAG CONTRIBUTION    same 50 failures, use_rag on vs off
#    difference in root-cause accuracy — the number that justifies the feature
#
# 5. ANOMALY             precision, recall, false-positive rate from
#    anomalies.status ('false_positive' is ground truth from real users)
#
# 6. COST & LATENCY      from ai_requests: p50/p95 latency, cost per analysis,
#    cache hit rate, classification source distribution
#
# 7. PROVIDER COMPARISON same 30 failures through gemini vs local qwen2.5-coder
#    accuracy, latency, cost, JSON validity rate
#
# 8. END-TO-END          time from pipeline failure to analysis visible
```

**The calibration curve is the most interesting result you will produce.** Bucket analyses by stated confidence and measure how often each bucket was actually right:

```text
Confidence bucket   n    Actually correct
0.90–1.00          22          91%          ← well calibrated
0.75–0.89          18          78%          ← well calibrated
0.60–0.74           7          57%          ← slightly overconfident
< 0.60              3          33%
```

If the model says 90% and is right 91% of the time, its confidence is *meaningful* and the UI is honest to display it. If it says 90% and is right 60% of the time, you have to say so — and either recalibrate or stop showing the number. This is a genuinely publishable-quality result for a student project, and it is the sort of thing an examiner remembers.

- [ ] `evaluate_all.py` written and run
- [ ] `reports/evaluation-final.md` committed with real numbers

---

## 23.2 Results to report honestly

| Metric | Realistic range | Note |
|---|---|---|
| Classification macro-F1 (hybrid) | 0.78 – 0.90 | Depends heavily on rare-class data |
| Root-cause accuracy | 0.65 – 0.85 | Graded by you; say who graded and how |
| RAG improvement | +5 – 15 points | Only measurable once you have history |
| Retrieval precision@3 | 0.70 – 0.90 | Sensitive to `embedding_input` |
| Anomaly false-positive rate | 0.10 – 0.30 | Report it; it will not be near zero |
| Cost per analysis | $0.002 – $0.01 | With caching |
| Cache hit rate | 25 – 50% | Rises with history |
| End-to-end latency p50 | 8 – 15 s | Webhook to analysis on screen |
| Failure prediction AUC | 0.55 – 0.70 | Likely weak — say so |

> **Write down the results you did not like.** A report claiming 96% on everything reads as untested. A report saying "the classifier reached 0.84 macro-F1 but only 0.41 on DEPLOYMENT because we had 38 examples, and here is the confusion matrix showing it collapsing into INFRASTRUCTURE" reads as someone who did the work. The second one survives questioning.

---

## 23.3 Report structure

```text
reports/stage/
├── 01-introduction.md          context, problem, objectives, scope
├── 02-state-of-the-art.md      AIOps, log anomaly detection, RCA, RAG,
│                               and the existing tools — GitLab Duo RCA,
│                               Datadog CI Visibility, Harness AIDA.
│                               Position PipeMind honestly against them.
├── 03-methodology.md           agile increments, the milestone plan, tooling
├── 04-architecture.md          four repos, layers, normalization, the AI boundary,
│                               ERD, sequence diagrams, technology justification
├── 05-implementation.md        ingestion, log processing, classification,
│                               embeddings, RAG, LLM, policy engine, UI
├── 06-ai.md                    the intelligence chapter: taxonomy, dataset,
│                               models, prompts, calibration
├── 07-experiments.md           every experiment, including the failed ones
├── 08-results.md               the evaluation, with the tables and plots
├── 09-limitations.md           what does not work and why
├── 10-conclusion.md            what was achieved, what comes next
└── annexes/                    schema, API reference, deployment
```

**Chapter 09 is not optional.** Be specific:

- The dataset is dominated by synthetic failures from a controlled lab, so real-world generalisation is unproven.
- Root-cause accuracy was graded by the author, not by an independent panel — a real bias.
- Historical intelligence needs history; a fresh deployment cannot demonstrate its main differentiator for weeks.
- Failure prediction underperformed and would need far more data to be useful.
- Only GitLab was tested against a live instance at scale; GitHub and Jenkins were validated against fixtures.
- Automated remediation was limited to levels 1–2 by choice; levels 3–4 were designed but not shipped.

An examiner who finds a limitation you did not mention doubts everything else. One who reads your limitations chapter and finds it already listed there trusts the whole document.

- [ ] Ten chapters written from what was actually built
- [ ] Every claim in the report traceable to a committed experiment

---

## 23.4 Diagrams

Committed as source (Mermaid / draw.io), exported to PNG.

| Diagram | Chapter |
|---|---|
| System architecture, four repos | 04 |
| ERD, 31 tables | 04 + annexe |
| Sequence: push → webhook → analysis → UI | 04 |
| Normalization: three providers → one model | 04 |
| Intelligence pipeline: redact → classify → RAG → LLM | 06 |
| RAG retrieval flow | 06 |
| Policy engine decision tree | 05 |
| Queue topology | 05 |
| Confusion matrix heatmap | 08 |
| Calibration curve | 08 |
| Cost/latency by provider | 08 |

- [ ] All diagrams generated, sources committed

---

## 23.5 Demo

A live demo of a distributed system in front of an audience is a coin flip. Engineer it.

**Script — 8 minutes:**

```text
0:00  The problem. Show a real 48,000-line failed pipeline log in GitLab.
      "Somewhere in here is one line that matters."

0:45  The workspace. Four projects, health at a glance.

1:30  Project board. KPIs, trends, the AI Insight card.

2:15  Break it live. Trigger FAIL_MODE=database in the lab.
      Switch to PipeMind and let the pipeline appear in real time.

3:15  The failure page. Observed vs Analysis. Read the root cause aloud.
      Point at the evidence — each item links to something real.

4:30  History. "This happened before." Open the 94% similar failure and
      show the resolution that worked.

5:15  Remediation. Show the recommendation, the policy gate, the approval.
      Approve it. Watch the retry run.

6:15  Anomaly. A passing pipeline flagged for a 4.1× duration.

6:45  Numbers. The evaluation table: F1, calibration, cost, latency.

7:30  Limitations, in one honest slide. Then the roadmap.
```

**Safety net — build all four:**

1. **Recorded fallback.** A screen recording of the full flow. If the network fails, you narrate the video. Nobody minds.
2. **Seeded demo workspace.** `php artisan pipemind:demo --reset` restores the exact state in 30 seconds.
3. **Pre-warmed analysis.** Run the demo failure once before you present so the signature is cached — the analysis returns instantly.
4. **Offline mode.** Everything runs on your laptop: lab GitLab, PipeMind, and Ollama as the LLM. No internet dependency at all.

> **Break it live if the room allows it, but never make the live break load-bearing.** The moment where you push a commit and PipeMind explains the failure before you finish talking is the one people remember — and the recorded version delivers the same story at zero risk.

- [ ] `pipemind:demo --reset` command
- [ ] Full run recorded
- [ ] Offline path tested end to end with Ollama
- [ ] Rehearsed three times, timed

---

## 23.6 Final checklist

```text
CODE
[ ] Four repos, README each, running from a clean clone in < 15 minutes
[ ] All tests green; CI green
[ ] No secrets in history (gitleaks over the full history, not just HEAD)
[ ] LICENSE + CONTRIBUTING

DATA REPO
[ ] schema.sql matches the live migrations (schema-check passes)
[ ] Datasets versioned with DATASET.md
[ ] Every experiment written up, including the failures
[ ] Evaluation results committed
[ ] Report complete
[ ] All diagrams exported

DEMO
[ ] Seeded workspace, recording, offline path, rehearsed
```

---

## Batch 3 complete — and the roadmap with it

Files 11–23 cover the frontend built from your two mockups, real-time updates, policy-gated remediation, anomaly detection, notifications and the assistant, the test suite, deployment, and the evaluation and report.

**What exists when every file is ticked:**

A DevOps engineer connects GitLab, pushes broken code, and within fifteen seconds PipeMind tells them what broke, shows the evidence, points at the commit that caused it, recalls the last time it happened and how it was fixed, proposes a change, and — inside a policy their team wrote — applies it and confirms the pipeline went green.

And a report that measures all of it honestly.
