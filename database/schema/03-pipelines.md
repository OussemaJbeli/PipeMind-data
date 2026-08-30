# Group 3 — Pipeline Domain

`pipelines` · `pipeline_stages` · `pipeline_jobs` · `pipeline_events` · `job_logs` · `commit_changes`

## Purpose

The normalised representation of CI/CD activity. GitLab, GitHub Actions and Jenkins all
model the same concepts differently; everything below is provider-agnostic, so the AI
layer never learns what a "workflow run" is.

## Key decisions

**`external_id` + `UNIQUE(project_id, external_id)`** makes ingestion idempotent.
A redelivered webhook updates rather than duplicates.

**`iid` is the display number** (`#821`) and is provider-specific. `external_id` is the
API identifier. They are different, and conflating them breaks deep links.

**`pipeline_events` is append-only.** It stores every raw delivery with its headers
(auth headers stripped) and a `UNIQUE(integration_id, external_delivery_id)` that makes
duplicate detection a database concern rather than application logic. It is also the
fastest-growing table — prune after 30 days.

**`job_logs` stores metadata, not bytes.** CI logs run 5–200 MB; the object itself lives
in MinIO/S3, immutable and unredacted so analysis stays reproducible. Postgres keeps the
path, checksum, redaction bookkeeping, and the extracted `excerpt` — the ~40 lines the
UI shows and the LLM sees.

**`commit_changes.is_config` / `is_dependency`** are computed at ingest from a path
pattern list. They are the single highest-signal feature for root-cause correlation:
*"the pipeline broke and `docker-compose.yml` changed"* is most of the diagnosis.

## Status normalisation

Ours is the only vocabulary that exists past the adapter layer:

`queued` · `running` · `success` · `failed` · `canceled` · `skipped` · `manual` · `timeout`

Two mappings worth remembering:

- GitLab reports a timeout as a plain `failed`; only `failure_reason=job_execution_timeout`
  distinguishes it. Timeouts matter because they are usually transient.
- Jenkins `UNSTABLE` means "built, but tests failed" → maps to `failed`, not `success`.

## Gotchas

- Two events for the same pipeline arrive within the same second. `ProcessPipelineEvent`
  must hold `WithoutOverlapping` on the pipeline's external id, or concurrent workers
  produce lost updates and duplicate jobs.
- Only fetch logs for `failed` and `canceled` jobs. Green-job logs are pure storage cost.
- Webhooks *will* be lost — a restart, a network blip, a provider outage. Scheduled
  reconciliation is not optional; without it the UI shows spinners forever.
