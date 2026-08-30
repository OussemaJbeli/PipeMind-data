# Group 7 — Metrics, Baselines, Anomalies

`project_metrics_daily` · `job_baselines` · `anomalies`

## Purpose

Every chart on the project board, and detection of problems in pipelines that
technically *succeed*.

## `project_metrics_daily`

A nightly rollup. The project board has eleven data regions; serving them from raw
`pipelines` scans a table that grows forever. Reading a handful of indexed rollup rows
stays fast at any history depth, and is why the whole board is one request.

`failures_by_category` (jsonb) drives the donut and the category bar list directly.

## `job_baselines` — "normal" is per project, per job, per branch

A 10-minute build is fine for one project and alarming for another.

**MAD is the primary spread measure, not standard deviation.** One 40-minute run caused
by a dead runner inflates stddev enough to hide every genuine anomaly for a month. Median
absolute deviation is unmoved by outliers — exactly the property you need in a metric
derived from noisy infrastructure.

Baselines use **successful runs only**. A failed job that died at 4 seconds would drag
the mean down and make every slow-but-passing run look normal.

Minimum 10 samples. Never flag against a baseline of three runs.

## `anomalies`

Eight detectors: duration, memory, failure_rate, retry_rate, queue_time, test_count,
log_size, flaky_test.

`deviation_ratio` is what the UI shows — "4.1× higher than normal" is readable in a way
that "modified z-score 9.2" is not, though both are stored.

**`false_positive` is a first-class status.** An anomaly detector nobody can push back on
gets ignored within a week. The rate feeds threshold tuning and belongs in the evaluation.

**Auto-resolve:** an open anomaly whose metric has been within 2 MAD for three
consecutive runs closes itself. Nobody acknowledges a stale alert, and an alert list
nobody trusts is worse than no alert list.
