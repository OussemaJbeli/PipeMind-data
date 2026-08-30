# 19 — Anomaly Detection & Analytics

**Repo:** `PipeMind-ai` + `PipeMind-back` + `PipeMind-front` · **Depends on:** 18 · **Milestone:** M4

Detect problems in pipelines that technically *succeed*, and give the team the analytics to see trends. This is the observability half of the platform.

---

## 19.1 Baselines

"Normal" is per project, per job, per branch. A 10-minute build is fine for one project and alarming for another.

```php
// spec — app/Console/Commands/ComputeJobBaselines.php  (daily 03:00)
// For each (project, job_name, ref) with ≥ 10 successful runs in 30 days:
//   mean, stddev, median, MAD, p95 of duration_seconds
//   mean peak_memory_mb where available
//   failure_rate, retry_rate
// Write to job_baselines. Also compute a ref='*' rollup as fallback.
//
// Use only SUCCESSFUL runs for duration baselines. A failed job that died at
// 4 seconds would drag the mean down and make every slow-but-passing run look normal.
```

> **Use MAD, not stddev, as the primary spread measure.** One 40-minute run caused by a dead runner inflates the standard deviation enough to hide every genuine anomaly for the next month. Median absolute deviation is unmoved by outliers, which is exactly the property you need in a metric derived from noisy infrastructure.

```python
# ready — app/services/anomaly.py
import numpy as np


def modified_zscore(value: float, median: float, mad: float) -> float:
    """Robust z-score. 0.6745 makes MAD comparable to a standard deviation."""
    if mad == 0:
        return 0.0
    return 0.6745 * (value - median) / mad


THRESHOLDS = {
    'low':      3.5,
    'medium':   5.0,
    'high':     8.0,
    'critical': 12.0,
}


def severity_for(score: float) -> str | None:
    s = abs(score)
    for name in ('critical', 'high', 'medium', 'low'):
        if s >= THRESHOLDS[name]:
            return name
    return None
```

- [ ] `ComputeJobBaselines` command, scheduled
- [ ] Minimum sample size enforced (≥ 10) — never flag against a baseline of three runs

---

## 19.2 Detectors

| Detector | Signal | Method |
|---|---|---|
| `duration` | Job or pipeline much slower than baseline | Modified z-score on duration |
| `memory` | Peak memory above baseline | Modified z-score, when the provider reports it |
| `failure_rate` | Project failure rate rising | 7-day vs 30-day rate, proportion test |
| `retry_rate` | A stable job starts retrying | Count in 24 h vs baseline |
| `queue_time` | Jobs waiting longer | Runner capacity signal |
| `test_count` | Test count dropped | Tests silently skipped — a real and easily missed regression |
| `flaky_test` | Same test, same commit, both outcomes | Direct query, no statistics needed |
| `log_size` | Log unusually large | Often a retry loop or a runaway warning |

```php
// spec — app/Console/Commands/DetectAnomalies.php  (every 10 min)
// For pipelines finished since the last run:
//   1. load baselines for each job
//   2. compute the modified z-score per metric
//   3. severity_for(score); skip if None
//   4. dedupe: one open anomaly per (project, job, type) — update, don't duplicate
//   5. create the anomaly, dispatch AnomalyDetected, write activity_log
//
// Auto-resolve: an open anomaly whose metric has been back within 2 MAD for
// 3 consecutive runs closes itself. Nobody acknowledges a stale alert, and an
// alert list nobody trusts is worse than no alert list.
```

```text
⚠ Build duration anomaly · biker-api · npm-build

  Observed    11m 04s
  Baseline    2m 42s   (median of 47 runs, 30d)
  Deviation   4.1× · modified z-score 9.2 · HIGH

  Possible causes
  · Dependency download slow or retried
  · Build cache miss
  · Runner resource contention

  Detected 4 minutes ago    [Investigate] [Acknowledge] [Not an issue]
```

**"Not an issue" is a first-class action.** It marks `false_positive`, which feeds threshold tuning. An anomaly detector nobody can push back on will be ignored within a week.

- [ ] Eight detectors implemented
- [ ] Dedupe and auto-resolve working
- [ ] False-positive rate tracked and reported in `PipeMind-data/experiments/anomaly-v1.md`

---

## 19.3 Failure prediction (optional — cut first if time is short)

```python
# spec — scripts/train_predictor.py
# Binary classifier: will this pipeline fail?
# Features available at pipeline START (no leakage — nothing from the run itself):
#   - files_changed, config_files_changed, dependency_files_changed
#   - lines_added, lines_deleted, files_touched
#   - author's 30-day failure rate on this project
#   - project failure rate last 7 days
#   - is_default_branch, source, hour_of_day, day_of_week
#   - time since last successful pipeline on this ref
#   - has the same signature failed in the last 24h
# Model: gradient boosting. Report ROC-AUC and precision@10%.
#
# BE HONEST IN THE REPORT. If AUC is 0.61, say so and explain why
# (small dataset, weak signal, class imbalance). A negative result you
# analysed well is worth more than an inflated number nobody believes.
```

> **The leakage trap:** it is trivially easy to include a feature computed after the pipeline ran (duration, job count, log size) and report 0.97 AUC. Every feature must be knowable at `queued_at`. Write the feature extractor to take only the pipeline's *creation-time* row and assert it in a test.

- [ ] Predictor trained and evaluated, or explicitly cut with a note in the report

---

## 19.4 Analytics view

`/app/projects/:slug/analytics`

```text
Analytics                                    [📅 Last 30 days ⌄] [Export CSV]

┌─ Failure trend ─────────────────────────┐ ┌─ MTTR trend ──────────────────┐
│ stacked area by category over time      │ │ line, with target band        │
└─────────────────────────────────────────┘ └───────────────────────────────┘

┌─ Failure heatmap ───────────────────────┐ ┌─ Slowest jobs ────────────────┐
│      Mon Tue Wed Thu Fri Sat Sun        │ │ npm-build    2m42s  ▲ 4.1×    │
│ 00h   ░   ░   ▒   ░   ░   ░   ░         │ │ integration  1m58s  ─         │
│ 09h   ▓   █   ▓   ▒   █   ░   ░         │ │ e2e-tests    1m12s  ▼         │
│ 18h   ▒   ▓   █   ▓   ▓   ░   ░         │ └───────────────────────────────┘
└─────────────────────────────────────────┘
                                            ┌─ Flakiest tests ──────────────┐
┌─ Top recurring signatures ──────────────┐ │ login.test.ts   7 flips  38%  │
│ DATABASE Connection refused   12  ✓known│ │ upload.spec.ts  3 flips  12%  │
│ DEPENDENCY Version conflict    8       │ └───────────────────────────────┘
└─────────────────────────────────────────┘

┌─ AI performance ────────────────────────────────────────────────────────┐
│ Analyses 312 · avg confidence 0.87 · helpful 84% · cache hits 41%       │
│ Cost $4.82 · avg latency 3.8s · classification: rules 62% ml 24% llm 14%│
└─────────────────────────────────────────────────────────────────────────┘
```

**The heatmap earns its place.** Failures clustering at 09:00 Monday and 18:00 Friday is a story about human behaviour — merge storms and end-of-week pushes — that no line chart tells. The "AI performance" strip is also where you get the numbers for your report without a separate script.

- [ ] `AnalyticsView` with six panels
- [ ] `PmHeatmap` component (day × hour)
- [ ] CSV export of the underlying rows for every panel

---

## Definition of Done

- [ ] A deliberately slowed job (add `sleep 300`) raises a duration anomaly within 10 min
- [ ] The anomaly shows observed vs baseline vs deviation ratio, with the sample size
- [ ] A recovered metric auto-resolves the anomaly
- [ ] "Not an issue" records a false positive
- [ ] Flaky detection catches a test that passes and fails on the same commit
- [ ] Analytics renders with 60 days of seeded history
- [ ] Anomaly evaluation (precision, false-positive rate) committed to `experiments/`

**Next:** [`20-notifications-assistant.md`](20-notifications-assistant.md)
