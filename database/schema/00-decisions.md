# Architecture Decisions

Locked in file 01. Each entry records the choice, the reason, and what it would cost to reverse.

| Date | Decision | Choice | Reason | Reversibility |
|---|---|---|---|---|
| 2026-08-30 | Embedding model | `all-MiniLM-L6-v2`, **384 dim** | CPU-only, no API key, ~90 MB, adequate for error text | **Hard** — fixes the `vector(384)` column. Mitigated by `failure_embeddings.model` + `UNIQUE(failure_id, model)`, which allow a second model to be backfilled alongside and compared before cutover. |
| 2026-08-30 | LLM provider | Abstraction over Gemini / OpenAI-compatible / Ollama / stub | Provider independence; the key is not yet available | **Easy** — one env var |
| 2026-08-30 | Starting LLM | `stub` → Gemini when the key arrives | Files 06–16 are fully buildable with no key | Easy |
| 2026-08-30 | Raw log storage | MinIO (S3 API) | Logs run 5–200 MB; Postgres keeps metadata + excerpt only | Medium — a disk swap plus a backfill |
| 2026-08-30 | Multi-tenancy | `team_id` on every tenant table, from day one | Retrofitting tenancy is a rewrite | Not reversible in practice |
| 2026-08-30 | Public identifiers | `uuid` column alongside a `bigint` PK | Do not leak row counts or permit enumeration | Easy |
| 2026-08-30 | Enums | `varchar` + `CHECK` constraint | Taxonomies grow; `ALTER TYPE` locks, a CHECK swap does not | Easy |
| 2026-08-30 | Primary CI platform | GitLab (local CE, or gitlab.com + tunnel) | Plain-text job logs, cleanest API, controllable failures | Easy — the adapter layer isolates it |
| 2026-08-30 | Redis client | `predis` (pure PHP) | `ext-redis` is not installed on the dev machine | Easy — set `REDIS_CLIENT=phpredis` |
| 2026-08-30 | Kafka / Spark | **Not implemented**; documented as a scaling path | Redis queues + Postgres handle this project's volume; the operational cost is not earned | Easy to add later |
| 2026-08-30 | `repositories` table | Folded into `projects` | 1:1 with a project in every supported provider; removes a join from hot queries | Medium |

## Host port allocation

This machine already runs a host PostgreSQL (5432), a host Redis (6379), and other
project containers (`shlink` on 8080, `shlink_db` on 5433, `devorc-postgres` on 5442).
PipeMind therefore publishes on non-default host ports. Container-internal ports are
unchanged, so nothing inside the stack is aware of this.

| Service | Host port | Container port | Note |
|---|---|---|---|
| PostgreSQL | **5434** | 5432 | 5432 host, 5433 shlink_db, 5442 devorc all taken |
| Redis | **6380** | 6379 | 6379 host redis-server |
| MinIO API | 9000 | 9000 | |
| MinIO console | 9001 | 9001 | |
| Mailpit SMTP | 1025 | 1025 | |
| Mailpit UI | 8025 | 8025 | |
| Laravel API | 8000 | — | `php artisan serve` |
| AI service | 8001 | 8001 | |
| Vite dev | 5173 | — | |
| Reverb (file 17) | **8081** | 8080 | 8080 taken by `shlink` |
| GitLab CE (lab) | 8929 | 8929 | started on demand only |
| Ollama (optional) | 11434 | 11434 | |

> Docker Compose reads `DB_PORT` and `REDIS_PORT` from `PipeMind-back/.env` — the same
> file Laravel reads. Host and container therefore cannot drift apart.

**Why this matters:** the first `docker compose up` silently started PostgreSQL *without*
publishing a port, because 5432 was already bound. The container was healthy, but Laravel
would have connected to the host PostgreSQL — no pgvector, no PipeMind schema — and
appeared almost-working while being entirely wrong. Always verify `docker compose ps`
shows a real `PORTS` value, not an empty column.

---

## `similarity_threshold` is 0.55, not 0.75

The roadmap's starting guess of 0.75 returns **zero rows** on realistic CI failures.
Across ten pairs the highest cosine similarity observed was 0.5865, so the guess made
retrieval silently return nothing at all — no error, no log, no failing test, just an
always-empty "similar failures" panel that is indistinguishable from a workspace with
no history yet.

Lowered to 0.55 and marked provisional. Full method, pair matrix and limitations in
[`experiments/similarity-threshold.md`](../../experiments/similarity-threshold.md).

Two settings must be kept in step: `SIMILARITY_THRESHOLD` in `PipeMind-ai/.env` (the
authoritative one, used by the query) and `pipemind.analysis.similarity_threshold` in
Laravel (display only).

## `find_similar_failures` ranks same-category neighbours above closer ones

Ordering is `resolved DESC, same_category DESC, distance`. Embeddings put two Node
failures near each other because they are both Node — in the pair matrix a Node database
error and a Node dependency error scored 0.5865, outranking the genuinely same-cause pair
at 0.5772. Category as a ranking key removes that artefact.

A hard `WHERE category = :category` filter was considered and rejected: a Docker failure
can genuinely present as a database symptom, and a hard filter makes that case unreachable.

## `failures.ecosystem` is stored, not re-derived

The AI service detects the ecosystem while processing a log and folds it into the
signature hash, but nothing persisted it — it was passed to `DetectFailure` and dropped.
At analysis time the embedding therefore could not be composed the same way the signature
was hashed, and retrieval quietly lost a dimension of context.

Added as a column on `failures` rather than on `failure_signatures`, because not every
failure has a signature (a failure with no error text never gets one) and the
embedding path needs the value per failure without a join.

## Tenancy for models with no `team_id`

`pipelines` and `pipeline_jobs` belong to a team only through their project, so `TeamScope`
has no column to filter on. Route model binding would resolve **any** team's UUID — and
`GET /jobs/{job}/log` returns log content, the most sensitive data in the system.

`Concerns\ScopedThroughProject` overrides `resolveRouteBinding` to constrain through the
project relation. Deliberately *not* a global scope: queued jobs and webhook ingestion
legitimately run with no team bound, and a global scope would make them silently return
nothing.

## The cache's warm path must respect feedback

`AnalysisCache::forget()` deletes the Redis key, but `get()` also has a database fallback
that looks for a recent confident analysis of the same signature. Without an exclusion,
purging the cache after a developer marks an analysis wrong achieves nothing — the very
next lookup resurrects the rejected analysis out of `analyses`.

`get()` now excludes any analysis carrying feedback with `was_helpful = false` or
`root_cause_correct = false`.

## `Http::preventStrayRequests()` in `Tests\TestCase`

An unfaked HTTP call used to reach the real network. On a machine running the AI service
on :8001 the suite passed or failed depending on what happened to be running locally —
three ingestion tests were silently talking to the live Python service. Tests that depend
on the outside world are not tests.

## Risk is assigned from `action_type`, in code

`recommender.sanitize()` overwrites whatever risk the model proposed, using the
`ACTION_RISK` table, and escalates one level on the default branch. A model asked politely
to be careful can still label a production rollback "low risk"; the policy engine that
decides what runs automatically must not depend on that politeness.

A test asserts `ACTION_RISK`'s keys equal the schema's `action_type` enum, because drift
there is silent: an action the schema allows but the table does not know degrades to
`manual` and quietly discards what the model proposed.
