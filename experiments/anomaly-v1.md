# Anomaly detection — v1

**Run:** 2026-09-06 · `pipemind:compute-baselines` then `pipemind:detect-anomalies --all`
**Corpus:** 335 terminal pipelines across 5 seeded projects, 114 job baselines.

## Why MAD and not standard deviation

CI durations are drawn from noisy shared infrastructure. One 40-minute run caused
by a dead runner inflates a standard deviation enough to hide every genuine
anomaly for the next month — the detector goes quiet exactly when something has
gone wrong.

The median absolute deviation is unmoved by that outlier. The modified z-score
`0.6745 · (x − median) / MAD` puts it on the same axis as a standard deviation, so
the thresholds below are calibrated in familiar units.

| Severity | Modified z-score |
|---|---|
| low | ≥ 3.5 |
| medium | ≥ 5.0 |
| high | ≥ 8.0 |
| critical | ≥ 12.0 |

`MAD = 0` returns a score of **0**, not infinity. A job that has genuinely never
varied would otherwise raise a permanent critical alert on its first one-second
wobble.

## The minimum sample size is the load-bearing rule

Baselines are only written for `(project, job, ref)` combinations with **≥ 10
successful runs in 30 days**. Below that, spread is meaningless and the detector
produces confident nonsense.

Verified directly: with three runs of history and a 9× slower run, the detector
writes **zero baselines and raises zero anomalies** — it declines to have an
opinion rather than guessing.

Duration statistics use **successful runs only**. A job that died after four
seconds would drag the mean down and make every slow-but-passing run look normal.
Failure and retry rates deliberately use *all* runs, since excluding failures
would make those rates structurally zero.

## A bug this corpus exposed immediately

The first implementation flagged memory with a hardcoded `ratio ≥ 1.5`, because
`job_baselines` stored only `mean_memory_mb` — there was no spread to measure
against.

On the first full run that produced **22 memory anomalies from 24 jobs**. A
threshold that fires on 92% of everything is not a detector; it is noise with a
severity label attached, and it would have buried the one real duration anomaly
sitting underneath it.

Fixed by storing `median_memory_mb` and `mad_memory` (migration
`2026_01_02_000003`) and giving memory the same modified z-score duration uses.

| | Before | After |
|---|---|---|
| Memory anomalies | 22 | **3** (all low) |
| Total anomalies | 24 | **5** |

## A second bug, in auto-resolve

`hasRecovered()` always compared **durations**, whatever the anomaly was about.
Nine memory anomalies closed themselves because the job's *runtime* had
recovered — a live alert discarded on the evidence of an unrelated measurement.

Auto-resolve is now metric-aware: a memory anomaly is closed only by memory
readings, against the memory median and MAD.

## Detection run

| Metric | Value |
|---|---|
| Pipelines scanned | 335 |
| Baselines written | 114 (all 114 now carry memory spread) |
| Anomalies raised | 5 |
| Auto-resolved in the same run | 5 |
| False positives marked by a human | 0 (nothing yet reviewed) |

Everything auto-resolved because the seeded history contains many healthy runs
after each deviation — which is itself the recovery path working.

## The injected slow job

The DoD's "add `sleep 300`" scenario, run against real baselines:

```
baseline npm-ci : median 73s, MAD 29.5s, n = 50 (ref=main)
injected run    : 383s

detected        : "npm-ci took 5.247x longer than usual"
                  observed 383s · baseline 73s · 5.247x · z = 6.242 · medium
                  method mad · status open
description     : "Ran in 6m 23s against a median of 1m 13s across 50 runs
                   in the last 30 days."
```

The **sample size in the description is not decoration**. "4× slower" measured
against three runs means nothing; "against a median of 50 runs" is a claim a
reader can weigh. Note also that it used the branch-specific baseline (n=50) over
the wildcard rollup (n=122) — an exact-ref baseline beats the fallback.

## Behaviours locked in by tests

`tests/Feature/Anomalies/DetectionTest.php`, 7 cases:

- A deliberately slowed job raises a duration anomaly with ratio, z-score and sample size.
- A thin baseline (3 runs) raises nothing at all.
- A job that got **faster** raises nothing — alerting on good news is how people learn to ignore the list.
- The same slow job across three pipelines updates **one** row rather than creating three.
- Severity never quietly falls: a critical alert that becomes "low" is how a real problem leaves the top of the list.
- Two healthy runs do **not** close an anomaly; three do. Absence of evidence is not recovery.
- A job that both passed and failed on the same commit is flagged flaky — a direct contradiction, no statistics needed.

`tests/Unit/StatisticsTest.php`, 10 cases, covering the zero-MAD guard, threshold
escalation, the consistency constant, and the proportion test refusing to draw a
conclusion from three runs.

## Limits

- **Seeded data, not production.** Durations are synthetic and more uniform than
  real CI. Thresholds should be revisited once the lab repository has produced a
  few weeks of genuine runs.
- **False-positive rate is not yet measurable.** It needs humans pressing "Not an
  issue", and nobody has used the UI. The `false_positive` status and the endpoint
  exist precisely so that number becomes available; it is not available now, and
  quoting one would be inventing it.
- **`queue_time` and `log_size` never fired** on this corpus — the seed has no
  queue delays and no large logs. Untested against real data.
- **`test_count` is a proxy.** It watches TEST-category failures disappearing
  rather than parsing test counts out of reports, which would need per-ecosystem
  result parsing.
