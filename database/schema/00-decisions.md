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
