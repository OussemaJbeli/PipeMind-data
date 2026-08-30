# 01 — Foundations

**Repo:** all · **Depends on:** — · **Milestone:** M1

Goal: `docker compose up` gives you Postgres+pgvector, Redis, MinIO and Mailpit, healthy, with a shared env convention across four repos. No application code yet.

---

## 1.1 Repo hygiene

- [ ] Rename `REDMI.md` → `README.md` in all four repos (`git mv REDMI.md README.md`)
- [ ] Fix `PipeMind-data/report.md` §39: it says *"Backend: Python FastAPI"* — change to **Laravel 12 (application/orchestration) + Python FastAPI (AI service only)**
- [ ] Add `.gitignore` per repo (see below)
- [ ] Add `.editorconfig` (shared, identical in all four)
- [ ] Create `develop` branch in each repo, protect `main`

```gitignore
# ready — PipeMind-back/.gitignore additions
/vendor
/node_modules
.env
.env.*
!.env.example
/storage/*.key
/storage/logs/*
/public/storage
.phpunit.result.cache
docker/data/
```

```gitignore
# ready — PipeMind-ai/.gitignore
__pycache__/
*.py[cod]
.venv/
.env
.env.*
!.env.example
/models/*.joblib
/models/*.pkl
!/models/.gitkeep
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

```gitignore
# ready — PipeMind-front/.gitignore
node_modules
dist
.env
.env.*
!.env.example
*.local
.vite
coverage
playwright-report
test-results
```

```gitignore
# ready — PipeMind-data/.gitignore
datasets/raw/**/*.log
datasets/raw/**/*.jsonl
!datasets/raw/.gitkeep
*.env
.DS_Store
__pycache__/
```

```ini
# ready — .editorconfig (all repos)
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{js,ts,vue,json,yml,yaml,css}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
```

---

## 1.2 Folder scaffolding in PipeMind-data

```bash
# ready
cd PipeMind-data
mkdir -p database/{schema,diagrams,seeds} \
         contracts/v1 \
         taxonomy \
         datasets/{raw,processed,classification,similarity,anomaly,evaluation} \
         experiments \
         research \
         reports/{stage,presentations} \
         scripts
find datasets -type d -exec touch {}/.gitkeep \;
touch database/diagrams/.gitkeep
```

- [ ] Scaffold created and committed

---

## 1.3 Docker Compose stack

Lives in `PipeMind-back/` (the backend owns infrastructure), but every service is on a shared external network so the AI and front containers can join.

```bash
# ready
docker network create pipemind || true
```

> **Check your host ports before you start.** A machine that already runs PostgreSQL,
> Redis, or other project containers will collide. Docker's failure mode here is
> nasty: the container starts and reports *healthy* while its port silently goes
> unpublished — so your app connects to the host's PostgreSQL instead, with no
> pgvector and no PipeMind schema, and looks almost-working.
>
> ```bash
> ss -tlnH | awk '{print $4}' | sed 's/.*://' | sort -un      # host listeners
> docker ps --format '{{.Names}} {{.Ports}}'                  # container bindings
> ```
>
> Pick free ports, set them in `.env` (Compose reads the same file), and after
> `up` confirm `docker compose ps` shows a real `PORTS` column — not an empty one.
> Record the allocation in `00-decisions.md`.

```yaml
# ready — PipeMind-back/docker-compose.yml
name: pipemind

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: pipemind-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_DATABASE:-pipemind}
      POSTGRES_USER: ${DB_USERNAME:-pipemind}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-secret}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"
    ports:
      - "${DB_PORT:-5434}:5432"   # host 5432/5433/5442 already taken here
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./docker/postgres/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USERNAME:-pipemind} -d ${DB_DATABASE:-pipemind}"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks: [pipemind]

  redis:
    image: redis:7-alpine
    container_name: pipemind-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy noeviction
    ports:
      - "${REDIS_PORT:-6380}:6379" # host redis-server holds 6379
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [pipemind]

  minio:
    image: minio/minio:latest
    container_name: pipemind-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_USER:-pipemind}
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD:-pipemind123}
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks: [pipemind]

  createbuckets:
    image: minio/mc:latest
    depends_on:
      minio: { condition: service_healthy }
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://minio:9000 ${MINIO_USER:-pipemind} ${MINIO_PASSWORD:-pipemind123};
      mc mb --ignore-existing local/pipemind-logs;
      mc mb --ignore-existing local/pipemind-artifacts;
      mc anonymous set download local/pipemind-artifacts;
      exit 0;
      "
    networks: [pipemind]

  mailpit:
    image: axllent/mailpit:latest
    container_name: pipemind-mailpit
    restart: unless-stopped
    ports:
      - "1025:1025"
      - "8025:8025"
    networks: [pipemind]

volumes:
  pgdata:
  redisdata:
  miniodata:

networks:
  pipemind:
    external: true
```

```sql
-- ready — PipeMind-back/docker/postgres/init/01-extensions.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS btree_gin;
```

- [ ] `docker-compose.yml` created
- [ ] `docker/postgres/init/01-extensions.sql` created
- [ ] `docker compose up -d` → all healthy
- [ ] MinIO console reachable at http://localhost:9001
- [ ] Mailpit reachable at http://localhost:8025

> **Why MinIO?** Raw CI logs run 5–200 MB. Putting them in Postgres `TEXT` destroys your query performance and your backups. Postgres stores the *metadata + extracted excerpt*; MinIO stores the immutable original. Swap the disk to real S3 in production by changing one env var.

> **Why `noeviction` on Redis?** Redis is the queue backend. If it evicts keys under memory pressure you silently lose jobs. Cache goes in a separate Redis database index, not a separate policy.

---

## 1.4 Local CI/CD target (GitLab in Docker)

You need a real CI platform you can break on demand. Self-hosted GitLab is the cleanest: plain-text job logs, a sane API, and full control.

```yaml
# ready — PipeMind-back/docker-compose.gitlab.yml   (separate file, start only when needed)
name: pipemind-ci

services:
  gitlab:
    image: gitlab/gitlab-ce:latest
    container_name: pipemind-gitlab
    restart: unless-stopped
    hostname: gitlab.local
    environment:
      GITLAB_OMNIBUS_CONFIG: |
        external_url 'http://gitlab.local'
        gitlab_rails['initial_root_password'] = 'PipeMind123!'
        prometheus_monitoring['enable'] = false
        gitlab_rails['gitlab_shell_ssh_port'] = 2222
    ports:
      - "8929:80"
      - "2222:22"
    volumes:
      - gitlab-config:/etc/gitlab
      - gitlab-logs:/var/log/gitlab
      - gitlab-data:/var/opt/gitlab
    shm_size: '256m'
    networks: [pipemind]

  gitlab-runner:
    image: gitlab/gitlab-runner:latest
    container_name: pipemind-runner
    restart: unless-stopped
    volumes:
      - runner-config:/etc/gitlab-runner
      - /var/run/docker.sock:/var/run/docker.sock
    networks: [pipemind]

volumes:
  gitlab-config:
  gitlab-logs:
  gitlab-data:
  runner-config:

networks:
  pipemind:
    external: true
```

- [ ] Add `127.0.0.1 gitlab.local` to `/etc/hosts`
- [ ] `docker compose -f docker-compose.gitlab.yml up -d` (needs ~4 GB RAM, takes ~5 min first boot)
- [ ] Log in at http://localhost:8929 as `root` / `PipeMind123!`
- [ ] Register the runner (`docker exec -it pipemind-runner gitlab-runner register`) with executor `docker`, image `docker:latest`
- [ ] Create a throwaway project `pipemind-lab` with a `.gitlab-ci.yml` that can pass or fail on demand

```yaml
# ready — the lab project's .gitlab-ci.yml — your failure generator
stages: [install, test, build]

variables:
  FAIL_MODE: "none"   # none | dependency | database | test | docker | timeout

install:
  stage: install
  image: node:20-alpine
  script:
    - if [ "$FAIL_MODE" = "dependency" ]; then npm install vue@2 vue-router@4; else echo ok; fi

test:
  stage: test
  image: node:20-alpine
  services:
    - name: postgres:16-alpine
      alias: db
  variables:
    POSTGRES_PASSWORD: test
  script:
    - if [ "$FAIL_MODE" = "database" ]; then nc -z db 5433 || (echo "ECONNREFUSED 172.20.0.4:5432"; exit 1); fi
    - if [ "$FAIL_MODE" = "test" ]; then echo "FAIL login.test.ts — Expected status 200, Received status 401"; exit 1; fi
    - if [ "$FAIL_MODE" = "timeout" ]; then sleep 3600; fi
    - echo "all tests passed"

build:
  stage: build
  image: docker:latest
  script:
    - if [ "$FAIL_MODE" = "docker" ]; then echo "no space left on device"; exit 1; fi
    - echo built
```

Trigger a specific failure with a manual pipeline run and `FAIL_MODE=database`. This is your dataset generator, your demo, and your integration test fixture — all three.

> If 4 GB of GitLab is too heavy on your machine, fall back to a **public GitHub repo with Actions** plus this same matrix. Cost is that GitHub log retrieval is a zip of per-step files (handled in file 05).

---

### Alternative: GitLab.com instead of local

**Default: run GitLab CE locally** (above). It gives you offline control, instant failure injection, and the most reliable demo. Budget ~4 GB RAM for it and ~8 GB for the rest of the stack.

If you are working on a machine that cannot spare it, gitlab.com's free tier is a drop-in substitute — same API, same plain-text logs, 400 free CI minutes/month:

1. Private project `pipemind-lab` with the `.gitlab-ci.yml` from 1.4.
2. Personal access token, scope `api`.
3. Tunnel your webhook endpoint so GitLab can reach it:

```bash
cloudflared tunnel --url http://localhost:8000    # no account needed
# or:  ngrok http 8000
```

4. Set the integration's `base_url` to `https://gitlab.com`, register the webhook against the tunnel URL.

Everything downstream is identical — the same `GitlabProvider`, the same normalization, the same logs. Only `base_url` differs. The free tunnel URL changes on restart, so re-run `POST /integrations/{id}/sync` when it does.

- [ ] CI target chosen and recorded in `00-decisions.md`

---

## 1.5 Shared env conventions

Every repo gets `.env.example` committed, `.env` ignored.

```bash
# ready — PipeMind-back/.env.example (delta from Laravel default)
APP_NAME=PipeMind
APP_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173

DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5434
DB_DATABASE=pipemind
DB_USERNAME=pipemind
DB_PASSWORD=secret

REDIS_HOST=127.0.0.1
REDIS_PORT=6380
REDIS_CLIENT=predis          # pure PHP, no ext-redis needed. Switch to phpredis only if you install the extension.
CACHE_STORE=redis
QUEUE_CONNECTION=redis
SESSION_DRIVER=redis

FILESYSTEM_DISK=logs
AWS_ACCESS_KEY_ID=pipemind
AWS_SECRET_ACCESS_KEY=pipemind123
AWS_DEFAULT_REGION=us-east-1
AWS_BUCKET=pipemind-logs
AWS_ENDPOINT=http://localhost:9000
AWS_USE_PATH_STYLE_ENDPOINT=true

MAIL_MAILER=smtp
MAIL_HOST=127.0.0.1
MAIL_PORT=1025

SANCTUM_STATEFUL_DOMAINS=localhost:5173
SESSION_DOMAIN=localhost

# --- PipeMind AI service ---
AI_SERVICE_URL=http://localhost:8001
AI_SERVICE_TOKEN=change-me-shared-secret
AI_SERVICE_TIMEOUT=120
AI_CONTRACT_VERSION=v1

# --- Provider defaults ---
GITLAB_DEFAULT_URL=http://gitlab.local
PIPEMIND_WEBHOOK_TOLERANCE_SECONDS=300
```

```bash
# ready — PipeMind-ai/.env.example
APP_ENV=local
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8001
SERVICE_TOKEN=change-me-shared-secret        # must equal AI_SERVICE_TOKEN in Laravel

DATABASE_URL=postgresql+psycopg://pipemind:secret@localhost:5434/pipemind
REDIS_URL=redis://localhost:6380/3

LLM_PROVIDER=gemini                          # gemini | ollama | openai_compatible
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b

EMBEDDING_PROVIDER=local                     # local | gemini
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384

MAX_LOG_CHARS=60000
MAX_CONTEXT_TOKENS=8000
LLM_TIMEOUT_SECONDS=90
LLM_MAX_RETRIES=2
MONTHLY_COST_CEILING_USD=25
REDACTION_STRICT=true
```

```bash
# ready — PipeMind-front/.env.example
VITE_API_URL=http://localhost:8000/api/v1
VITE_WS_HOST=localhost
VITE_WS_PORT=8081
VITE_APP_NAME=PipeMind
VITE_ENABLE_ASSISTANT=false
```

- [ ] Three `.env.example` files committed
- [ ] `.env` copied from each and filled locally

---

## 1.6 Task runner

```makefile
# ready — PipeMind-back/Makefile
.PHONY: up down restart logs migrate fresh seed queue test shell psql redis

up:        ; docker compose up -d && docker compose ps
down:      ; docker compose down
restart:   ; docker compose restart
logs:      ; docker compose logs -f --tail=100
migrate:   ; php artisan migrate
fresh:     ; php artisan migrate:fresh --seed
seed:      ; php artisan db:seed
queue:     ; php artisan horizon
serve:     ; php artisan serve --port=8000
test:      ; php artisan test
psql:      ; docker exec -it pipemind-postgres psql -U pipemind -d pipemind
redis:     ; docker exec -it pipemind-redis redis-cli
gitlab-up: ; docker compose -f docker-compose.gitlab.yml up -d
```

- [ ] Makefile created, `make up` works

---

## 1.7 Decisions locked here

Record these in `PipeMind-data/database/schema/00-decisions.md` — they drive the schema in file 02.

| Decision | Choice | Reason |
|---|---|---|
| Embedding model | `all-MiniLM-L6-v2`, **384 dim** | Runs on CPU, fast, good enough for error text. Fixed by the schema, so decide now; swap later via the `failure_embeddings.model` column |
| Raw log storage | MinIO/S3 | Logs are large and immutable; Postgres keeps metadata + excerpt |
| Multi-tenancy | Yes, `team_id` from day one | Retrofitting tenancy is a rewrite |
| Primary CI platform | Self-hosted GitLab CE (gitlab.com as fallback) | Plain-text logs, controllable failures, cleanest API |
| LLM provider | Gemini (cloud) now, Ollama (local) later — both supported | `LLMProvider` abstraction; swap with one env var. Start on `stub` until the key arrives |
| Embedding provider | **Local** `all-MiniLM-L6-v2`, 384 dim | Independent of the LLM choice. CPU-only, no key, no internet — free similarity search from day one |
| Public IDs | UUID column alongside bigint PK | Don't leak row counts or allow enumeration |

- [ ] `00-decisions.md` written

---

## Definition of Done

```bash
docker compose up -d
docker compose ps                      # all services healthy
docker exec pipemind-postgres psql -U pipemind -d pipemind -c "\dx"
# must list: vector, pg_trgm, uuid-ossp, btree_gin
docker exec pipemind-redis redis-cli ping    # PONG
curl -s http://localhost:9000/minio/health/live -o /dev/null -w "%{http_code}\n"   # 200
```

- [ ] All four checks pass
- [ ] Committed on `develop` in each repo

**Next:** [`02-database-schema.md`](02-database-schema.md)
