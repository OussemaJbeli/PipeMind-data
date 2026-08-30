# 22 — Deployment & CI/CD

**Repo:** all · **Depends on:** 21 · **Milestone:** ship

Production deployment, and PipeMind's own pipeline — analysed by PipeMind. That last part is the best demo you have.

---

## 22.1 PipeMind's own CI

```yaml
# ready — .gitlab-ci.yml (per repo; this one is PipeMind-back)
stages: [quality, test, build, deploy, notify]

variables:
  DOCKER_DRIVER: overlay2
  POSTGRES_DB: pipemind_test
  POSTGRES_USER: pipemind
  POSTGRES_PASSWORD: secret

.php: &php
  image: php:8.3-cli
  before_script:
    - apt-get update -qq && apt-get install -y -qq git unzip libpq-dev
    - docker-php-ext-install pdo_pgsql
    - curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer
    - composer install --no-interaction --prefer-dist --no-progress
  cache:
    key: composer-$CI_COMMIT_REF_SLUG
    paths: [vendor/]

lint:
  <<: *php
  stage: quality
  script: [vendor/bin/pint --test]

analyse:
  <<: *php
  stage: quality
  script: [vendor/bin/phpstan analyse --memory-limit=1G]

secrets:
  stage: quality
  image: zricethezav/gitleaks:latest
  script: [gitleaks detect --source . --verbose --redact]

test:
  <<: *php
  stage: test
  services:
    - name: pgvector/pgvector:pg16
      alias: postgres
    - name: redis:7-alpine
      alias: redis
  variables:
    DB_HOST: postgres
    REDIS_HOST: redis
  script:
    - php artisan key:generate
    - php artisan migrate --force
    - php artisan pipemind:schema-check      # docs and migrations must agree
    - vendor/bin/pest --coverage --min=75
  coverage: '/Total:\s+(\d+\.\d+)\s?%/'
  artifacts:
    reports:
      junit: report.xml

build:
  stage: build
  image: docker:latest
  services: [docker:dind]
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

deploy:
  stage: deploy
  script: [./deploy.sh $CI_COMMIT_SHA]
  environment: { name: production, url: https://pipemind.example }
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: manual

# The dogfooding step. PipeMind watches its own pipelines, so a failure here
# produces a PipeMind analysis — which is both a real test of the product and
# the most persuasive thing you can show in a demo.
notify-pipemind:
  stage: notify
  image: curlimages/curl:latest
  when: always
  script:
    - |
      curl -sS -X POST "$PIPEMIND_WEBHOOK_URL" \
        -H "X-PipeMind-Token: $PIPEMIND_TOKEN" \
        -H 'Content-Type: application/json' \
        -d "{\"event\":\"pipeline\",\"provider\":\"gitlab\",\"external_id\":\"$CI_PIPELINE_ID\",
             \"status\":\"$CI_JOB_STATUS\",\"ref\":\"$CI_COMMIT_REF_NAME\",
             \"commit\":{\"sha\":\"$CI_COMMIT_SHA\",\"message\":\"$CI_COMMIT_TITLE\"}}"
```

- [ ] CI pipeline per repo, all stages green
- [ ] PipeMind monitors its own repositories

---

## 22.2 Production compose

```yaml
# ready — docker-compose.prod.yml (shape)
services:
  caddy:          # TLS termination + static frontend + reverse proxy
  app:            # php-fpm, replicas: 2
  nginx:          # in front of php-fpm
  horizon:        # queue workers
  scheduler:      # php artisan schedule:work
  reverb:         # websockets
  ai:             # FastAPI, replicas: 2
  postgres:       # pgvector, with a real backup sidecar
  redis:
  minio:
```

```caddyfile
# ready — Caddyfile
pipemind.example {
    encode gzip zstd

    handle /api/*         { reverse_proxy nginx:80 }
    handle /sanctum/*     { reverse_proxy nginx:80 }
    handle /broadcasting/* { reverse_proxy nginx:80 }
    handle /webhooks/*    { reverse_proxy nginx:80 }
    handle /app/*         { reverse_proxy reverb:8080 }   # ws upgrade

    handle {
        root * /srv/frontend
        try_files {path} /index.html
        file_server
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }
}
```

**The AI service is never exposed publicly.** No port mapping, internal network only. Its only client is Laravel.

---

## 22.3 Production checklist

```text
SECURITY
[ ] APP_DEBUG=false, APP_ENV=production
[ ] APP_KEY generated and backed up — losing it makes every encrypted
    credential in the database permanently unreadable
[ ] All secrets from the environment or a secret store, never in an image
[ ] AI service unreachable from outside the internal network
[ ] Webhook endpoints rate-limited, signature verification mandatory
[ ] HTTPS enforced; HSTS on
[ ] Postgres and Redis not port-mapped to the host
[ ] MinIO bucket private; downloads via signed URLs only
[ ] Horizon dashboard gated to owners

RELIABILITY
[ ] Health checks on every service; restart: unless-stopped
[ ] Queue workers supervised; failed_jobs monitored
[ ] Postgres backups: nightly dump + WAL archiving, restore TESTED
[ ] MinIO lifecycle: raw logs expire after 90 days
[ ] Log rotation configured
[ ] Reconciliation scheduled — webhooks WILL be lost

OBSERVABILITY
[ ] Prometheus scraping Laravel, the AI service and Horizon
[ ] Grafana: ingestion rate, queue depth, analysis latency, AI cost, error rate
[ ] Alerts: queue depth > 500, failed_jobs > 10, AI budget > 80%,
    no webhook events in 1h, disk > 85%
[ ] Sentry (or equivalent) on all three services

DATA
[ ] Migrations run with --force in a release step, never at container start
[ ] pipemind:prune scheduled
[ ] Restore drill performed at least once and written up
```

> **Test the restore, not the backup.** An untested backup is a hypothesis. Restore into a scratch database, run the schema check, and confirm a failure analysis still renders — then you know.

---

## 22.4 Deploy script

```bash
# ready — deploy.sh
set -euo pipefail
TAG="${1:?usage: deploy.sh <tag>}"

echo "→ pulling ${TAG}"
docker compose -f docker-compose.prod.yml pull

echo "→ migrating"
docker compose -f docker-compose.prod.yml run --rm app php artisan migrate --force

echo "→ schema check"
docker compose -f docker-compose.prod.yml run --rm app php artisan pipemind:schema-check

echo "→ rolling app"
docker compose -f docker-compose.prod.yml up -d --no-deps --scale app=2 app nginx

echo "→ restarting workers so they load the new code"
docker compose -f docker-compose.prod.yml up -d --no-deps horizon scheduler reverb ai

echo "→ warming caches"
docker compose -f docker-compose.prod.yml exec -T app php artisan config:cache
docker compose -f docker-compose.prod.yml exec -T app php artisan route:cache
docker compose -f docker-compose.prod.yml exec -T app php artisan event:cache

echo "→ health"
curl -fsS https://pipemind.example/api/health
```

> **Restart Horizon on every deploy.** Queue workers are long-lived PHP processes that hold the old code in memory. A deploy that skips this leaves workers running yesterday's jobs against today's schema — a genuinely confusing class of bug.

- [ ] Production compose + Caddyfile + deploy script written
- [ ] Deployed to a real host (a €5 VPS is enough)
- [ ] Checklist completed

**Next:** [`23-evaluation-report.md`](23-evaluation-report.md)
