# PipeMind — Implementation Roadmaps

Executable build plan. Each file is **one work session**: open it, follow it top to bottom, tick the boxes, commit, move to the next.

Derived from [`../roadmap.md`](../roadmap.md) (the strategic phases). This folder is the *tactical* version — actual schemas, actual endpoints, actual dependencies, actual components.

---

## How to use

1. Files are numbered. **Do them in order.** Later files assume earlier ones are done.
2. Every file ends with a **Definition of Done** — a command you run that proves the step works. Do not move on until it passes.
3. `[ ]` boxes are the atomic tasks. Tick them in the file itself as you go — this folder is your progress tracker.
4. Code blocks marked `# ready` are meant to be copy-pasted as-is. Blocks marked `# spec` describe what to write.

---

## Order

| # | File | Repo | Output | Depends on |
|---|------|------|--------|-----------|
| 01 | [`01-foundations.md`](01-foundations.md) | all | Docker Compose stack, env conventions, tooling | — |
| 02 | [`02-database-schema.md`](02-database-schema.md) | data | Complete schema: 31 tables, relations, indexes, enums | 01 |
| 03 | [`03-backend-setup.md`](03-backend-setup.md) | back | Laravel 12, migrations, models, factories, seeders, Horizon | 02 |
| 04 | [`04-backend-auth-api.md`](04-backend-auth-api.md) | back | Sanctum auth, teams, RBAC, workspace + project endpoints | 03 |
| 05 | [`05-backend-ingestion.md`](05-backend-ingestion.md) | back | Provider adapters, webhooks, normalization, queue jobs, log storage | 04 |
| 06 | [`06-ai-service-setup.md`](06-ai-service-setup.md) | ai | FastAPI service, dependencies, config, Docker, contract | 05 |
| 07 | [`07-ai-log-processing.md`](07-ai-log-processing.md) | ai | Redaction, log processor, signature generation | 06 |
| 08 | [`08-ai-classification.md`](08-ai-classification.md) | ai + data | Rule engine, dataset, ML training + evaluation scripts | 07 |
| 09 | [`09-ai-llm-rag.md`](09-ai-llm-rag.md) | ai | LLM providers, prompts, embeddings, pgvector, similarity, RAG | 08 |
| 10 | [`10-backend-ai-integration.md`](10-backend-ai-integration.md) | back | AI gateway, analysis jobs, persistence, caching, cost tracking | 09 |
| 11 | [`11-frontend-setup.md`](11-frontend-setup.md) | front | Vite + Vue 3 + TS + Tailwind, API client, stores, routing | 04 |
| 12 | [`12-frontend-design-system.md`](12-frontend-design-system.md) | front | Design tokens, base components, charts, icons | 11 |
| 13 | [`13-frontend-public-auth.md`](13-frontend-public-auth.md) | front | Landing, login, register, onboarding wizard | 12 |
| 14 | [`14-frontend-workspace.md`](14-frontend-workspace.md) | front | **Workspace page** (`ui/workspace.png`) | 12 |
| 15 | [`15-frontend-project.md`](15-frontend-project.md) | front | **Project board** (`ui/project.png`) | 12 |
| 16 | [`16-frontend-failure-investigation.md`](16-frontend-failure-investigation.md) | front | Pipelines, jobs, log viewer, failure detail, AI analysis | 15 |
| 17 | [`17-realtime.md`](17-realtime.md) | back + front | Reverb/Echo, live pipeline + analysis updates | 16 |
| 18 | [`18-remediation.md`](18-remediation.md) | back + front | Policy engine, approvals, audit trail | 17 |
| 19 | [`19-anomaly-analytics.md`](19-anomaly-analytics.md) | ai + back + front | Baselines, anomaly detection, analytics pages | 18 |
| 20 | [`20-notifications-assistant.md`](20-notifications-assistant.md) | all | Slack/email, ⌘K search, AI assistant | 19 |
| 21 | [`21-testing-quality.md`](21-testing-quality.md) | all | Pest, pytest, Vitest, Playwright, factories | 20 |
| 22 | [`22-deployment-cicd.md`](22-deployment-cicd.md) | all | Own CI/CD, prod compose, monitoring | 21 |
| 23 | [`23-evaluation-report.md`](23-evaluation-report.md) | data | Metrics run, experiments, stage report, demo script | 22 |

All 24 files written. **Batch 1** = 00–05 (foundation + backend) · **Batch 2** = 06–10 (AI layer) · **Batch 3** = 11–23 (frontend + ship)

---

## Milestone mapping

| Milestone | Files | Done when |
|---|---|---|
| **M1 Skeleton** | 01–04, 11–13 | Login works, seeded projects render in Vue |
| **M2 Observer** | 05, 14, 15 | Real GitLab pipeline ingested and visible on the project board |
| **M3 Analyst** ⭐ | 06–10, 16 | Real failure → redacted → classified → LLM → analysis on screen |
| **M4 Memory** | 09 (RAG half), 19 | Similar failures retrieved and improving analyses |
| **M5 Assistant** | 17, 18, 20 | Policy-gated remediation approved from the UI |

**M3 is the project.** Protect it.

---

## Repository map

```text
PipMind/
├── PipeMind-back/    Laravel 12 · PHP 8.3 · PostgreSQL · Redis · queues · API
├── PipeMind-ai/      Python 3.11 · FastAPI · ML · embeddings · LLM
├── PipeMind-front/   Vue 3 · TypeScript · Vite · Tailwind
└── PipeMind-data/    schema · datasets · taxonomy · contracts · research · reports
    ├── roadmaps/     ← you are here
    ├── ui/           target mockups
    ├── database/     ERD + per-table docs
    ├── contracts/    versioned Laravel ↔ Python API contract
    ├── datasets/     classification / similarity / anomaly / evaluation
    ├── taxonomy/     failure categories
    └── reports/      stage report
```

---

## Conventions

**Git** — `main` (protected) ← `develop` ← `feat/*` `fix/*` `chore/*`.
Conventional commits: `feat(back): add gitlab webhook controller`.

**Naming**
| Layer | Style | Example |
|---|---|---|
| DB tables | snake_case plural | `pipeline_jobs` |
| DB columns | snake_case | `duration_seconds` |
| Laravel models | StudlyCase singular | `PipelineJob` |
| API routes | kebab-case plural | `/api/v1/failure-signatures` |
| API JSON | snake_case | `success_rate` |
| Vue components | PascalCase | `PipelineStatusPill.vue` |
| Vue composables | `useThing` | `usePipelinePolling.ts` |
| TS types | PascalCase | `FailureAnalysis` |
| Python modules | snake_case | `log_processor.py` |

**Timestamps** — always UTC in DB, ISO-8601 in API, localize in the browser only.
**IDs** — `bigint` PK internally; public `uuid` column on every user-facing entity. Never expose sequential IDs in URLs.
**Money/metrics** — `decimal(10,6)` for cost, `integer` seconds for durations, never floats for money.

---

## Design tokens (locked from `ui/*.png`)

```css
/* ready — copy into PipeMind-front/src/assets/tokens.css in file 12 */
:root {
  --pm-bg:          #0A0B0E;   /* app background            */
  --pm-sidebar:     #0C0E12;   /* sidebar / rail            */
  --pm-surface:     #101318;   /* card                      */
  --pm-surface-2:   #161A21;   /* nested card / hover       */
  --pm-border:      #1F242C;   /* hairline                  */
  --pm-border-soft: #171B22;

  --pm-text:        #E7EAF0;   /* primary text              */
  --pm-text-dim:    #8B93A1;   /* labels, meta              */
  --pm-text-mute:   #5C6472;   /* disabled                  */

  --pm-accent:      #A9E831;   /* lime — CTA, active, brand */
  --pm-accent-hi:   #C6F55A;
  --pm-accent-dim:  rgba(169,232,49,0.12);

  --pm-success:     #4ADE80;
  --pm-danger:      #F04438;
  --pm-warning:     #F5A524;
  --pm-running:     #6366F1;   /* indigo — in-progress      */
  --pm-ai:          #A855F7;   /* purple — AI/analysis      */
  --pm-info:        #38BDF8;

  --pm-radius:      12px;
  --pm-radius-lg:   16px;
  --pm-font:        'Inter', system-ui, -apple-system, sans-serif;
  --pm-font-mono:   'JetBrains Mono', 'Fira Code', monospace;
}
```

Category colors (used by donut, bars, pills — must be identical across all charts):

| Category | Hex |
|---|---|
| DATABASE | `#A9E831` |
| TEST | `#F04438` |
| DEPENDENCY | `#F5A524` |
| DOCKER | `#38BDF8` |
| NETWORK | `#6366F1` |
| BUILD | `#EC4899` |
| DEPLOYMENT | `#14B8A6` |
| CONFIGURATION | `#A855F7` |
| AUTHENTICATION | `#F97316` |
| PERMISSION | `#8B5CF6` |
| INFRASTRUCTURE | `#0EA5E9` |
| RESOURCE | `#EAB308` |
| UNKNOWN | `#5C6472` |

---

## AI providers — cloud and local

Two **independent** choices, both supported from day one:

| | Options | Key needed | Where it runs |
|---|---|---|---|
| **LLM** — reasoning, root cause | Gemini · OpenAI-compatible · **Ollama (local)** · `stub` | Cloud only | API or your machine |
| **Embeddings** — similarity, RAG | **`all-MiniLM-L6-v2` (local, default)** · Gemini | No | CPU, in the image |

**Current plan:** Gemini for reasoning, local embeddings. Ollama added later without any code change.

**No key yet?** Set `LLM_PROVIDER=stub`. Files 06, 07, 08, the retrieval half of 09, and the entire frontend (11–16) are fully buildable with no key, no network and no cost. Swapping to Gemini is one env var — see file 06 §6.9.

---

## Non-negotiables (repeat from `../roadmap.md`)

1. Redaction runs **before** any external LLM call. No exceptions.
2. The LLM never holds credentials or shell access. Laravel is the execution boundary.
3. Every AI claim carries evidence + confidence + a link to the raw log line.
4. Evaluate with numbers, not impressions.
5. Raw logs are immutable. Analysis must be reproducible.
6. `team_id` on every tenant-scoped table, enforced by a global scope — from day one.
