# PipeMind — Development Roadmap

Build order from empty repos to a defensible, demoable platform.
Rule: **every phase must end with something runnable**. No phase is "design only".

> **Tactical version:** [`roadmaps/`](roadmaps/00-INDEX.md) — the same plan as executable step-by-step files (schemas, endpoints, dependencies, components).

Stack locked: Vue 3 + TS + Vite + Tailwind · Laravel 12 + PHP 8.3 · Python 3.11 + FastAPI · PostgreSQL 16 + pgvector · Redis 7 · Docker Compose.

---

## Phase 0 — Foundations (infra before code)

- [ ] `docker-compose.yml` in `PipeMind-back`: postgres(pgvector), redis, mailpit, minio (logs), adminer
- [ ] Fix stack contradiction in `report.md` §39 (says FastAPI backend) → Laravel is the backend, Python is AI-only
- [ ] `.env.example` conventions shared across the 3 code repos
- [ ] Decide + document: internal auth between Laravel ↔ Python (shared secret header, private network)
- [ ] Makefile / `dev.sh`: `up`, `down`, `migrate`, `seed`, `logs`, `test`
- [ ] Git conventions: branch naming, conventional commits, PR template
- [ ] **Deliverable:** `docker compose up` → postgres + redis healthy

## Phase 1 — Data model (the real starting point)

- [ ] ERD in `PipeMind-data/database/diagrams/erd.png` (dbdiagram.io / Mermaid source committed)
- [ ] Core tables: `users`, `teams`, `projects`, `integrations`, `repositories`
- [ ] Pipeline tables: `pipelines`, `pipeline_stages`, `pipeline_jobs`, `pipeline_events`
- [ ] Log tables: `job_logs` (pointer to object storage, not raw text in Postgres), `log_artifacts`
- [ ] Intelligence tables: `failures`, `failure_signatures`, `analyses`, `analysis_evidence`, `recommendations`, `remediations`, `remediation_policies`
- [ ] Support tables: `notifications`, `ai_requests` (cost/latency/token audit), `knowledge_documents`
- [ ] Vector table: `failure_embeddings` (pgvector, `vector(768)` or `vector(1536)` — pick after embedding model choice)
- [ ] **Key design decision:** `failure_signature` = normalized error fingerprint hash → dedupe + clustering + cache key
- [ ] Document each table in `PipeMind-data/database/schema/*.md`
- [ ] Failure taxonomy v1 as a committed enum list (`PipeMind-data/taxonomy/failure-categories.md`)
- [ ] **Deliverable:** ERD + schema docs reviewed *before* writing a single migration

## Phase 2 — Database + backend skeleton

- [ ] `laravel new` + PostgreSQL connection + pgvector extension migration
- [ ] All migrations from Phase 1 + Eloquent models + relationships + factories
- [ ] Seeders: demo user, demo project, 3 fake pipelines (green / red / flaky)
- [ ] Redis wired: cache, session, queue driver
- [ ] `php artisan queue:work` container in compose + Horizon (queue observability, free demo win)
- [ ] Auth: Sanctum (SPA token), register/login/me, roles (owner / member / viewer)
- [ ] API skeleton: `/api/projects`, `/api/pipelines` (list + show, seeded data only)
- [ ] API resources + versioning under `/api/v1`
- [ ] **Deliverable:** login via curl, list seeded pipelines as JSON

## Phase 3 — Ingestion (this is the DevOps heart)

- [ ] Provider adapter interface: `PipelineProvider` (fetchPipeline, fetchJobs, fetchLogs, retryJob)
- [ ] **GitLab first** — cleanest API + best logs (`/projects/:id/jobs/:id/trace` returns plain text)
- [ ] Webhook endpoint `POST /api/v1/webhooks/{provider}/{integration_uuid}` + signature verification
- [ ] Normalization layer: GitLab/GitHub/Jenkins → common `Pipeline / Stage / Job / Status` model
- [ ] Generic webhook `POST /api/v1/events/pipeline` for unsupported platforms
- [ ] Queue jobs: `ProcessPipelineEvent` → `FetchPipelineLogs` → `StoreLog` → `DetectFailure`
- [ ] Log storage: MinIO/S3 for raw, Postgres for metadata + extracted excerpt
- [ ] Encrypted integration tokens (Laravel `encrypted` cast), never in logs
- [ ] Idempotency: same webhook delivered twice must not duplicate a pipeline
- [ ] Then **GitHub Actions** (logs come as a zip of per-step files — handle unzip)
- [ ] Then **Jenkins** (consoleText endpoint + a `post { failure { curl } }` snippet documented)
- [ ] **Deliverable:** push to a real test repo → pipeline appears in DB with logs attached, no UI needed

## Phase 4 — Log processing + AI service skeleton

- [ ] `PipeMind-ai`: FastAPI + pydantic + uv/poetry + Dockerfile + `/health`
- [ ] Freeze the contract `POST /v1/analyze` (request + response models) — versioned, in `PipeMind-data/contracts/`
- [ ] **Secret redaction FIRST** (before any LLM call): regex + entropy detection for tokens, passwords, connection strings, JWTs, AWS keys
- [ ] Log processor: ANSI strip, timestamp strip, noise removal, tail extraction, error-block detection
- [ ] Stack trace extraction per ecosystem (node, php, python, java, go, docker, kubectl)
- [ ] Error signature generation (normalize numbers/paths/UUIDs → hash) — shared with Laravel
- [ ] Laravel `AiGateway` service + `AnalyzeFailure` job calling the Python service
- [ ] **Deliverable:** a 40k-line log → ~40 relevant lines + a signature hash

## Phase 5 — Classification (start dumb, prove it, then upgrade)

- [ ] Rule-based classifier v1: ~60 regex patterns → 13 categories (this alone covers a lot)
- [ ] Build the labeled dataset in `PipeMind-data/datasets/classification/`
- [ ] Bootstrap labels with an LLM, then hand-verify a stratified sample (this is your data-quality story)
- [ ] Synthetic failure generator: real docker-compose stacks with injected faults → real logs, known root cause
- [ ] ML v2: TF-IDF + LogisticRegression/LinearSVC baseline, `scripts/train.py` + `scripts/evaluate.py`
- [ ] Report precision/recall/F1 **per class** + confusion matrix (class imbalance is the trap)
- [ ] Only then consider embeddings/transformer v3 — and only if it beats the baseline on the same holdout
- [ ] **Deliverable:** a measured comparison table in `PipeMind-data/experiments/`

## Phase 6 — LLM reasoning

- [ ] `LLMProvider` abstraction: `GeminiProvider`, `OllamaProvider`, `OpenAICompatibleProvider`
- [ ] Structured output enforcement (JSON schema / function calling) + pydantic validation + one retry on parse failure
- [ ] Prompt/context builder: project tech + branch + commit + changed files + failed job + processed log + classification
- [ ] Response cache keyed by `failure_signature` + project → same error twice costs nothing
- [ ] Cost/latency/token logging into `ai_requests` (needed for the report AND for sanity)
- [ ] Timeouts, retries with backoff, graceful degradation (AI down ≠ pipeline failed)
- [ ] **Deliverable:** real failure → structured JSON with root cause, evidence, confidence, recommendations

## Phase 7 — Historical intelligence (the actual differentiator)

- [ ] Embedding model choice (`all-MiniLM-L6-v2` local, or Gemini embeddings) — document the tradeoff
- [ ] Embed every failure signature on creation → `failure_embeddings` (pgvector, HNSW index)
- [ ] Similarity search endpoint `POST /v1/similar` with cosine distance + score threshold
- [ ] Feed top-K similar *resolved* failures into the LLM context = RAG
- [ ] Knowledge base ingestion: project README, CI config, runbooks → chunked + embedded
- [ ] Resolution feedback loop: developer marks "this fixed it" → becomes retrieval-eligible knowledge
- [ ] Measure retrieval quality (precision@k) on a held-out set, don't just eyeball it
- [ ] **Deliverable:** "this resembles failure #921 from 3 months ago, fixed by X"

## Phase 8 — Frontend (start in parallel from Phase 2's API)

- [ ] `npm create vite@latest` — Vue 3 + TS + Tailwind + Pinia + Vue Router + Axios client
- [ ] Generate/maintain TS types from the Laravel API contract (single source of truth)
- [ ] Auth flow + protected routes + interceptor
- [ ] Layout + design tokens (dark-first, developer-tool aesthetic — not a card soup)
- [ ] Dashboard: health summary, failure rate, recent failures, category breakdown
- [ ] Project list + project detail
- [ ] Pipeline view: stage/job graph with live status
- [ ] **Failure detail page — the flagship screen:** observed facts / AI analysis / evidence / similar failures / recommendations, visually separated
- [ ] Raw log viewer with the AI-highlighted region anchored
- [ ] Confidence + uncertainty rendered honestly (never "AI magic")
- [ ] Real-time: Laravel Reverb / Echo over WebSocket (fallback: polling with backoff)
- [ ] Distinct error states: pipeline failed vs analysis failed vs provider down vs analysis running
- [ ] **Deliverable:** full click-through from dashboard → failure → recommendation

## Phase 9 — Recommendation + controlled remediation

- [ ] Recommendation model: action, reason, risk, affected files, confidence
- [ ] **Policy engine in Laravel** (never in the LLM): action → risk → auto-allowed / needs-approval / forbidden
- [ ] Level 1 (recommend) → Level 2 (approve then execute) — stop here for v1
- [ ] Safe actions only at first: retry job, retry pipeline, create issue
- [ ] Approval UI + full audit trail (who approved, what ran, what happened)
- [ ] Later + optional: patch generation → branch → merge request (never direct push to main)
- [ ] **Never:** LLM holding infrastructure credentials or executing arbitrary commands
- [ ] **Deliverable:** approve a retry from the UI, watch it re-run in GitLab

## Phase 10 — Anomaly detection + prediction

- [ ] Per-project rolling baselines: duration, memory, retry count, test count
- [ ] Statistical detection first (z-score / MAD on a moving window) — cheap and explainable
- [ ] Isolation Forest as the "ML" upgrade, evaluated against the statistical baseline
- [ ] Flaky test detection: same test, same commit, different outcome
- [ ] Failure prediction at pipeline start (features: changed files, dep changes, author history, recent failure rate)
- [ ] Be honest in the report if prediction underperforms — a negative result is a valid result
- [ ] **Deliverable:** "build is 4.1× slower than this project's normal" on a *passing* pipeline

## Phase 11 — Delivery surface

- [ ] Notifications: Slack webhook + email, with the analysis summary and a deep link
- [ ] CLI (`pipemind analyze`, `pipemind status`) — small Python click app reusing the API
- [ ] Prometheus metrics + Grafana dashboard (ingestion rate, analysis latency, AI cost, failure rate)
- [ ] Optional / only if time remains: VS Code extension

## Phase 12 — Hardening, evaluation, report

- [ ] Tests: Pest (backend), pytest (AI), Vitest + one Playwright happy path (front)
- [ ] Its own CI/CD — PipeMind's pipeline analyzed by PipeMind (best demo you have)
- [ ] Rate limiting, webhook replay protection, secret scanning in CI
- [ ] Full evaluation run: classification F1, retrieval precision@k, root-cause accuracy on a labeled set, latency, cost/analysis
- [ ] Load test: 100 concurrent pipeline events
- [ ] `PipeMind-data/reports/stage/` written from what was actually built and measured
- [ ] Demo script + seeded demo environment that fails on demand

---

## Milestones

| # | Name | Definition of done |
|---|------|--------------------|
| M1 | Skeleton | Compose up, migrations, auth, seeded API |
| M2 | Observer | Real GitLab pipeline ingested with logs, visible in Vue |
| M3 | **Analyst (MVP)** | Real failure → redacted → classified → LLM → structured analysis on screen |
| M4 | Memory | Embeddings + similarity + RAG improving analyses, feedback loop closed |
| M5 | Assistant | Recommendations + policy-gated approved remediation + anomalies + notifications |

**M3 is the project.** Everything after it is depth. Protect M3's date.

---

## Parallelization

```text
Phase 0 → 1 → 2 ────┬──► 3 ──► 4 ──► 5 ──► 6 ──► 7 ──► 9 ──► 10
                    └──► 8 (frontend, continuous from M1 onward)
```

---

## Cut list (scope control)

Drop these first if time runs short — in this order:

1. VS Code extension
2. Kafka + Spark (Redis queues + Postgres handle this project's volume; add Kafka **only** if a "Big Data" requirement is graded — then use it as an ingestion buffer with a documented justification)
3. Failure prediction (Phase 10 second half)
4. Automated remediation Levels 3–4
5. Jenkins integration (GitLab + GitHub already prove provider independence)
6. Transformer classifier (keep the measured TF-IDF baseline + LLM fallback)
7. CLI

---

## Decisions to lock before Phase 1

- [ ] Embedding model + vector dimension (drives the schema)
- [ ] Raw log storage: MinIO vs Postgres `TEXT` (recommend MinIO — logs get huge)
- [ ] Multi-tenant from day one? (recommend yes — `team_id` on every table, cheap now, painful later)
- [ ] Primary demo CI platform (recommend GitLab self-hosted in Docker — full control, generate failures on demand)
- [ ] Default LLM provider + a hard monthly cost ceiling

---

## Non-negotiables

- Redaction runs **before** any external LLM call. No exceptions.
- The LLM never gets credentials or shell access. The backend is the execution boundary.
- Every AI claim carries evidence, confidence, and a link to the raw log.
- Evaluate with numbers, not impressions.
- Store raw logs immutably — analysis is reproducible, or it isn't science.
