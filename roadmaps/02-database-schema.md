# 02 — Database Schema

**Repo:** data (design) → back (implementation in file 03) · **Depends on:** 01 · **Milestone:** M1

The complete data model: **31 domain tables** across 8 groups. This is the canonical reference. Laravel migrations in file 03 must match it exactly.

> **Design rule:** enums are `varchar` + `CHECK` constraint, not native PG `ENUM` types. Adding a value to a native enum requires `ALTER TYPE` and locks; a CHECK constraint is a one-line migration. Failure taxonomies *will* grow.

---

## Entity map

```text
users ──< team_user >── teams ──< team_invitations
                          │
                          ├──< integrations ──< projects
                          │                       │
                          ├──< ai_providers       ├──< pipelines ──< pipeline_stages
                          ├──< notification_channels │                     │
                          ├──< remediation_policies  │              ┌──────┴──────┐
                          ├──< knowledge_documents   │              │             │
                          │        └──< knowledge_chunks     pipeline_jobs   commit_changes
                          ├──< failure_signatures    │              │
                          ├──< activity_logs         │              └──< job_logs
                          └──< ai_requests           │
                                                     ├──< pipeline_events
                                                     ├──< project_metrics_daily
                                                     ├──< job_baselines
                                                     ├──< anomalies
                                                     │
                                                     └──< failures ──┬──< analyses ──┬──< analysis_evidence
                                                          │          │               ├──< recommendations ──< remediations
                                                          │          │               └──< analysis_feedback
                                                          │          └──< failure_embeddings
                                                          └── signature_id → failure_signatures
```

---

## Group 1 — Identity & tenancy

```sql
-- ready
CREATE TABLE users (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    name                VARCHAR(120) NOT NULL,
    email               VARCHAR(190) NOT NULL UNIQUE,
    email_verified_at   TIMESTAMPTZ,
    password            VARCHAR(255) NOT NULL,
    avatar_url          VARCHAR(500),
    job_title           VARCHAR(120),
    timezone            VARCHAR(64) NOT NULL DEFAULT 'UTC',
    locale              VARCHAR(10) NOT NULL DEFAULT 'en',
    theme               VARCHAR(10) NOT NULL DEFAULT 'dark'
                        CHECK (theme IN ('dark','light','system')),
    current_team_id     BIGINT,
    onboarded_at        TIMESTAMPTZ,
    last_login_at       TIMESTAMPTZ,
    last_login_ip       INET,
    remember_token      VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ
);

CREATE TABLE teams (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    name                VARCHAR(120) NOT NULL,
    slug                VARCHAR(120) NOT NULL UNIQUE,
    owner_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    logo_url            VARCHAR(500),
    plan                VARCHAR(20) NOT NULL DEFAULT 'free'
                        CHECK (plan IN ('free','pro','enterprise')),
    -- privacy_mode drives whether logs may ever reach an external LLM
    privacy_mode        VARCHAR(20) NOT NULL DEFAULT 'cloud_redacted'
                        CHECK (privacy_mode IN ('cloud_redacted','local_only')),
    settings            JSONB NOT NULL DEFAULT '{}'::jsonb,
    monthly_ai_budget_usd NUMERIC(10,2) NOT NULL DEFAULT 25.00,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ
);

ALTER TABLE users
  ADD CONSTRAINT users_current_team_fk
  FOREIGN KEY (current_team_id) REFERENCES teams(id) ON DELETE SET NULL;

CREATE TABLE team_user (
    id          BIGSERIAL PRIMARY KEY,
    team_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL DEFAULT 'member'
                CHECK (role IN ('owner','admin','member','viewer')),
    invited_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, user_id)
);

CREATE TABLE team_invitations (
    id          BIGSERIAL PRIMARY KEY,
    uuid        UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    email       VARCHAR(190) NOT NULL,
    role        VARCHAR(20) NOT NULL DEFAULT 'member'
                CHECK (role IN ('admin','member','viewer')),
    token       VARCHAR(64) NOT NULL UNIQUE,
    invited_by  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, email)
);
```

**Role capability matrix** (enforced by Laravel policies in file 04):

| Capability | owner | admin | member | viewer |
|---|:--:|:--:|:--:|:--:|
| View projects, pipelines, failures, analyses | ✓ | ✓ | ✓ | ✓ |
| Trigger AI analysis | ✓ | ✓ | ✓ | — |
| Retry job / pipeline | ✓ | ✓ | ✓ | — |
| Approve remediation | ✓ | ✓ | — | — |
| Manage projects & integrations | ✓ | ✓ | — | — |
| Manage AI providers & budget | ✓ | ✓ | — | — |
| Manage members & roles | ✓ | ✓ | — | — |
| Edit remediation policies | ✓ | — | — | — |
| Delete team | ✓ | — | — | — |

---

## Group 2 — Integrations & projects

```sql
-- ready
CREATE TABLE integrations (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id             BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    provider            VARCHAR(20) NOT NULL
                        CHECK (provider IN ('gitlab','github','jenkins','generic')),
    name                VARCHAR(120) NOT NULL,
    base_url            VARCHAR(255),                 -- self-hosted GitLab / Jenkins root
    -- Laravel 'encrypted' cast. NEVER logged, NEVER returned by the API.
    credentials         TEXT,
    webhook_secret      VARCHAR(128) NOT NULL,        -- generated by us, given to the provider
    scopes              JSONB NOT NULL DEFAULT '[]'::jsonb,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','active','error','disabled')),
    last_verified_at    TIMESTAMPTZ,
    last_event_at       TIMESTAMPTZ,
    last_error          TEXT,
    settings            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by          BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ
);

CREATE TABLE projects (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id             BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    integration_id      BIGINT REFERENCES integrations(id) ON DELETE SET NULL,
    name                VARCHAR(120) NOT NULL,
    slug                VARCHAR(140) NOT NULL,
    description         TEXT,
    -- provider identity
    external_id         VARCHAR(190),                 -- GitLab project id / GitHub owner-repo
    external_path       VARCHAR(255),                 -- group/subgroup/project
    repository_url      VARCHAR(500),
    web_url             VARCHAR(500),
    default_branch      VARCHAR(120) NOT NULL DEFAULT 'main',
    -- presentation (drives the project card in ui/workspace.png)
    icon                VARCHAR(40) NOT NULL DEFAULT 'code',
    color               VARCHAR(9) NOT NULL DEFAULT '#A9E831',
    tech_stack          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ["Laravel","Docker","GitLab"]
    -- behaviour
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    auto_analyze        BOOLEAN NOT NULL DEFAULT TRUE,
    analyze_on_branches JSONB NOT NULL DEFAULT '["*"]'::jsonb,
    ai_provider_id      BIGINT,                       -- FK added after ai_providers exists
    settings            JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- denormalised counters, refreshed by ProjectStatsJob (avoids N aggregate queries on the workspace grid)
    pipelines_count     INTEGER NOT NULL DEFAULT 0,
    success_rate        NUMERIC(5,2) NOT NULL DEFAULT 0,
    failures_today      INTEGER NOT NULL DEFAULT 0,
    last_pipeline_id    BIGINT,
    last_pipeline_at    TIMESTAMPTZ,
    health_status       VARCHAR(20) NOT NULL DEFAULT 'unknown'
                        CHECK (health_status IN ('healthy','degraded','failing','unknown')),
    created_by          BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,
    UNIQUE (team_id, slug),
    UNIQUE (integration_id, external_id)
);
```

> **No separate `repositories` table.** A project maps 1:1 to a repository in every provider we support. The original design sketch listed it; folding it into `projects` removes a join from every hot query. Revisit only if monorepo-multi-pipeline support becomes real.

> **Why denormalised counters on `projects`?** The workspace grid renders N project cards, each needing success rate, failures today, pipeline count and last pipeline. That is 4×N aggregates over a table that grows forever. Cache them on the row; recompute on pipeline completion and on a 5-minute schedule. `health_status` is derived: `failing` if last pipeline failed, `degraded` if success_rate < 90%, else `healthy`.

---

## Group 3 — Pipeline domain

```sql
-- ready
CREATE TABLE pipelines (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    project_id          BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    external_id         VARCHAR(190) NOT NULL,        -- provider pipeline/run id
    iid                 INTEGER,                      -- display number: #821
    provider            VARCHAR(20) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','running','success','failed',
                                          'canceled','skipped','manual','timeout')),
    source              VARCHAR(30) NOT NULL DEFAULT 'push'
                        CHECK (source IN ('push','merge_request','schedule','manual',
                                          'api','tag','web','trigger','unknown')),
    ref                 VARCHAR(255) NOT NULL,        -- branch or tag
    is_tag              BOOLEAN NOT NULL DEFAULT FALSE,
    commit_sha          VARCHAR(64),
    commit_short_sha    VARCHAR(12),
    commit_message      TEXT,
    commit_author_name  VARCHAR(190),
    commit_author_email VARCHAR(190),
    commit_url          VARCHAR(500),
    web_url             VARCHAR(500),
    triggered_by        VARCHAR(190),
    queued_at           TIMESTAMPTZ,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    duration_seconds    INTEGER,
    queue_seconds       INTEGER,
    jobs_total          SMALLINT NOT NULL DEFAULT 0,
    jobs_failed         SMALLINT NOT NULL DEFAULT 0,
    jobs_succeeded      SMALLINT NOT NULL DEFAULT 0,
    attempt             SMALLINT NOT NULL DEFAULT 1,
    retry_of_id         BIGINT REFERENCES pipelines(id) ON DELETE SET NULL,
    has_failure         BOOLEAN NOT NULL DEFAULT FALSE,
    raw_payload         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, external_id)
);

CREATE TABLE pipeline_stages (
    id                  BIGSERIAL PRIMARY KEY,
    pipeline_id         BIGINT NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    name                VARCHAR(120) NOT NULL,
    position            SMALLINT NOT NULL DEFAULT 0,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','running','success','failed',
                                          'canceled','skipped','manual')),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    duration_seconds    INTEGER,
    jobs_count          SMALLINT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pipeline_id, name)
);

CREATE TABLE pipeline_jobs (
    id                  BIGSERIAL PRIMARY KEY,
    uuid                UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    pipeline_id         BIGINT NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    stage_id            BIGINT REFERENCES pipeline_stages(id) ON DELETE SET NULL,
    external_id         VARCHAR(190) NOT NULL,
    name                VARCHAR(190) NOT NULL,
    stage_name          VARCHAR(120) NOT NULL,
    position            SMALLINT NOT NULL DEFAULT 0,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','running','success','failed',
                                          'canceled','skipped','manual','timeout')),
    failure_reason      VARCHAR(80),                  -- provider's own reason string
    exit_code           SMALLINT,
    allow_failure       BOOLEAN NOT NULL DEFAULT FALSE,
    is_retryable        BOOLEAN NOT NULL DEFAULT TRUE,
    attempt             SMALLINT NOT NULL DEFAULT 1,
    runner_name         VARCHAR(190),
    runner_tags         JSONB NOT NULL DEFAULT '[]'::jsonb,
    image               VARCHAR(255),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    duration_seconds    INTEGER,
    queue_seconds       INTEGER,
    -- resource telemetry, when the provider exposes it (drives anomaly detection)
    peak_memory_mb      INTEGER,
    cpu_seconds         INTEGER,
    web_url             VARCHAR(500),
    log_fetched         BOOLEAN NOT NULL DEFAULT FALSE,
    raw_payload         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pipeline_id, external_id)
);

-- Raw webhook deliveries. Append-only. Idempotency + replay + debugging.
CREATE TABLE pipeline_events (
    id                    BIGSERIAL PRIMARY KEY,
    uuid                  UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    integration_id        BIGINT REFERENCES integrations(id) ON DELETE CASCADE,
    project_id            BIGINT REFERENCES projects(id) ON DELETE CASCADE,
    pipeline_id           BIGINT REFERENCES pipelines(id) ON DELETE SET NULL,
    provider              VARCHAR(20) NOT NULL,
    event_type            VARCHAR(60) NOT NULL,       -- pipeline / build / workflow_run / job
    external_delivery_id  VARCHAR(190),               -- X-GitHub-Delivery, X-Gitlab-Event-UUID
    external_object_id    VARCHAR(190),
    signature_valid       BOOLEAN NOT NULL DEFAULT FALSE,
    payload               JSONB NOT NULL,
    headers               JSONB NOT NULL DEFAULT '{}'::jsonb,
    processing_status     VARCHAR(20) NOT NULL DEFAULT 'pending'
                          CHECK (processing_status IN ('pending','processing','processed',
                                                       'failed','skipped','duplicate')),
    processing_error      TEXT,
    attempts              SMALLINT NOT NULL DEFAULT 0,
    received_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at          TIMESTAMPTZ,
    UNIQUE (integration_id, external_delivery_id)
);

-- Metadata only. The bytes live in MinIO/S3.
CREATE TABLE job_logs (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              BIGINT NOT NULL UNIQUE REFERENCES pipeline_jobs(id) ON DELETE CASCADE,
    pipeline_id         BIGINT NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    project_id          BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    storage_disk        VARCHAR(40) NOT NULL DEFAULT 'logs',
    storage_path        VARCHAR(500) NOT NULL,        -- logs/{project_uuid}/{pipeline_iid}/{job_id}.log
    size_bytes          BIGINT NOT NULL DEFAULT 0,
    line_count          INTEGER NOT NULL DEFAULT 0,
    checksum_sha256     CHAR(64),
    -- redaction bookkeeping
    is_redacted         BOOLEAN NOT NULL DEFAULT FALSE,
    redaction_count     SMALLINT NOT NULL DEFAULT 0,
    redaction_types     JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- what the log processor extracted (this is what the UI shows and the LLM sees)
    excerpt             TEXT,
    excerpt_start_line  INTEGER,
    excerpt_end_line    INTEGER,
    error_block         TEXT,
    stack_trace         TEXT,
    truncated           BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at          TIMESTAMPTZ,
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Files touched by the pipeline's commit. Drives "changed files" evidence.
CREATE TABLE commit_changes (
    id            BIGSERIAL PRIMARY KEY,
    pipeline_id   BIGINT NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    project_id    BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_path     VARCHAR(500) NOT NULL,
    change_type   VARCHAR(12) NOT NULL
                  CHECK (change_type IN ('added','modified','deleted','renamed','copied')),
    old_path      VARCHAR(500),
    additions     INTEGER NOT NULL DEFAULT 0,
    deletions     INTEGER NOT NULL DEFAULT 0,
    language      VARCHAR(40),
    is_config     BOOLEAN NOT NULL DEFAULT FALSE,     -- docker-compose.yml, .env, *.ci.yml …
    is_dependency BOOLEAN NOT NULL DEFAULT FALSE,     -- package.json, composer.lock, go.mod …
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pipeline_id, file_path)
);
```

> `is_config` and `is_dependency` are computed at ingest from a path pattern list. They are the single highest-signal feature for root-cause correlation — *"the pipeline broke and `docker-compose.yml` changed"* is most of the diagnosis.

---

## Group 4 — Failure & intelligence

```sql
-- ready
-- The deduplication spine. One row per distinct normalized error, per team.
CREATE TABLE failure_signatures (
    id                     BIGSERIAL PRIMARY KEY,
    uuid                   UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id                BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    hash                   CHAR(64) NOT NULL,          -- sha256 of normalized_error
    normalized_error       TEXT NOT NULL,              -- numbers/paths/uuids/hex → placeholders
    sample_error           TEXT NOT NULL,              -- one real unredacted-position example
    category               VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN',
    subcategory            VARCHAR(60),
    occurrence_count       INTEGER NOT NULL DEFAULT 1,
    projects_affected      SMALLINT NOT NULL DEFAULT 1,
    first_seen_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- once a resolution is confirmed, future matches short-circuit straight to it
    is_known               BOOLEAN NOT NULL DEFAULT FALSE,
    known_root_cause       TEXT,
    known_resolution       TEXT,
    resolution_confirmed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    resolution_confirmed_at TIMESTAMPTZ,
    avg_resolution_seconds INTEGER,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, hash)
);

CREATE TABLE failures (
    id                      BIGSERIAL PRIMARY KEY,
    uuid                    UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id                 BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id              BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    pipeline_id             BIGINT NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    job_id                  BIGINT REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    signature_id            BIGINT REFERENCES failure_signatures(id) ON DELETE SET NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'detected'
                            CHECK (status IN ('detected','queued','analyzing','analyzed',
                                              'analysis_failed','resolved','ignored')),
    severity                VARCHAR(10) NOT NULL DEFAULT 'medium'
                            CHECK (severity IN ('low','medium','high','critical')),
    category                VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN',
    subcategory             VARCHAR(60),
    stage_name              VARCHAR(120),
    job_name                VARCHAR(190),
    error_message           TEXT,
    error_type              VARCHAR(120),
    exit_code               SMALLINT,
    is_flaky                BOOLEAN NOT NULL DEFAULT FALSE,
    is_transient            BOOLEAN NOT NULL DEFAULT FALSE,
    occurrence_index        INTEGER NOT NULL DEFAULT 1,  -- nth time this signature hit this project
    failed_at               TIMESTAMPTZ NOT NULL,
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- resolution
    resolved_at             TIMESTAMPTZ,
    resolved_by             BIGINT REFERENCES users(id) ON DELETE SET NULL,
    resolution_type         VARCHAR(20)
                            CHECK (resolution_type IN ('fixed','retried','ignored',
                                                       'auto_remediated','flaky','unresolved')),
    resolution_note         TEXT,
    resolution_commit_sha   VARCHAR(64),
    time_to_resolution_seconds INTEGER,                  -- feeds the MTTR tile
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE analyses (
    id                      BIGSERIAL PRIMARY KEY,
    uuid                    UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    failure_id              BIGINT NOT NULL REFERENCES failures(id) ON DELETE CASCADE,
    team_id                 BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    status                  VARCHAR(20) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','running','completed','failed','cached')),
    contract_version        VARCHAR(10) NOT NULL DEFAULT 'v1',
    ai_service_version      VARCHAR(20),
    -- conclusions
    category                VARCHAR(30),
    subcategory             VARCHAR(60),
    severity                VARCHAR(10),
    confidence              NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),
    summary                 VARCHAR(500),
    root_cause              TEXT,
    explanation             TEXT,
    is_transient            BOOLEAN NOT NULL DEFAULT FALSE,
    retry_recommended       BOOLEAN NOT NULL DEFAULT FALSE,
    -- provenance: which techniques actually produced this
    classification_source   VARCHAR(20)
                            CHECK (classification_source IN ('rules','ml','llm','hybrid')),
    classification_confidence NUMERIC(4,3),
    used_rag                BOOLEAN NOT NULL DEFAULT FALSE,
    similar_failures_count  SMALLINT NOT NULL DEFAULT 0,
    -- cost & performance
    model_provider          VARCHAR(30),
    model_name              VARCHAR(80),
    prompt_tokens           INTEGER,
    completion_tokens       INTEGER,
    cost_usd                NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms              INTEGER,
    cache_hit               BOOLEAN NOT NULL DEFAULT FALSE,
    raw_response            JSONB,
    error                   TEXT,
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every claim must point at something real. This table is what makes the AI trustworthy.
CREATE TABLE analysis_evidence (
    id             BIGSERIAL PRIMARY KEY,
    analysis_id    BIGINT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    type           VARCHAR(24) NOT NULL
                   CHECK (type IN ('log_line','changed_file','historical_failure',
                                   'metric','config','dependency','commit','doc')),
    content        TEXT NOT NULL,
    source_ref     VARCHAR(500),      -- "job_logs#L1284" | "docker-compose.yml" | "failure:uuid"
    line_number    INTEGER,
    related_failure_id BIGINT REFERENCES failures(id) ON DELETE SET NULL,
    weight         NUMERIC(4,3) NOT NULL DEFAULT 0.5,
    position       SMALLINT NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE recommendations (
    id             BIGSERIAL PRIMARY KEY,
    uuid           UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    analysis_id    BIGINT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    failure_id     BIGINT NOT NULL REFERENCES failures(id) ON DELETE CASCADE,
    title          VARCHAR(255) NOT NULL,
    description    TEXT,
    rationale      TEXT,
    action_type    VARCHAR(30) NOT NULL
                   CHECK (action_type IN ('retry_job','retry_pipeline','investigate',
                                          'edit_file','update_config','update_dependency',
                                          'create_issue','create_merge_request',
                                          'rollback_deployment','manual')),
    risk           VARCHAR(10) NOT NULL DEFAULT 'medium'
                   CHECK (risk IN ('low','medium','high','critical')),
    confidence     NUMERIC(4,3),
    affected_files JSONB NOT NULL DEFAULT '[]'::jsonb,
    patch          TEXT,                                -- unified diff, when generated
    action_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    position       SMALLINT NOT NULL DEFAULT 0,
    status         VARCHAR(20) NOT NULL DEFAULT 'proposed'
                   CHECK (status IN ('proposed','accepted','rejected','applied','failed','expired')),
    decided_by     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    decided_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The learning loop: did PipeMind get it right?
CREATE TABLE analysis_feedback (
    id                 BIGSERIAL PRIMARY KEY,
    analysis_id        BIGINT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    was_helpful        BOOLEAN NOT NULL,
    root_cause_correct BOOLEAN,
    correct_category   VARCHAR(30),          -- ground-truth label → feeds the training set
    actual_root_cause  TEXT,
    actual_resolution  TEXT,
    comment            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (analysis_id, user_id)
);
```

> **`analysis_feedback.correct_category` is your labeled dataset.** Every correction a developer makes is a free, in-domain training example. Export it in file 08. This is the mechanism that makes the classifier improve without manual labeling sessions.

---

## Group 5 — Remediation

```sql
-- ready
-- Deterministic rules. The LLM proposes; this table decides. Never the other way round.
CREATE TABLE remediation_policies (
    id            BIGSERIAL PRIMARY KEY,
    team_id       BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id    BIGINT REFERENCES projects(id) ON DELETE CASCADE,   -- NULL = team default
    action_type   VARCHAR(30) NOT NULL,
    mode          VARCHAR(20) NOT NULL DEFAULT 'approval'
                  CHECK (mode IN ('auto','approval','forbidden')),
    max_risk      VARCHAR(10) NOT NULL DEFAULT 'low'
                  CHECK (max_risk IN ('low','medium','high','critical')),
    min_confidence NUMERIC(4,3) NOT NULL DEFAULT 0.800,
    max_per_day   SMALLINT NOT NULL DEFAULT 5,
    allowed_branches JSONB NOT NULL DEFAULT '["*"]'::jsonb,
    blocked_branches JSONB NOT NULL DEFAULT '["main","master","production"]'::jsonb,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, project_id, action_type)
);

CREATE TABLE remediations (
    id                 BIGSERIAL PRIMARY KEY,
    uuid               UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id            BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id         BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    failure_id         BIGINT NOT NULL REFERENCES failures(id) ON DELETE CASCADE,
    recommendation_id  BIGINT REFERENCES recommendations(id) ON DELETE SET NULL,
    action_type        VARCHAR(30) NOT NULL,
    risk               VARCHAR(10) NOT NULL,
    policy_decision    VARCHAR(20) NOT NULL
                       CHECK (policy_decision IN ('auto_allowed','requires_approval','forbidden')),
    policy_reason      VARCHAR(255),
    status             VARCHAR(20) NOT NULL DEFAULT 'pending_approval'
                       CHECK (status IN ('pending_approval','approved','rejected','queued',
                                         'executing','succeeded','failed','cancelled','expired')),
    payload            JSONB NOT NULL DEFAULT '{}'::jsonb,
    result             JSONB,
    error              TEXT,
    requested_by       BIGINT REFERENCES users(id) ON DELETE SET NULL,   -- NULL = system/AI
    approved_by        BIGINT REFERENCES users(id) ON DELETE SET NULL,
    approved_at        TIMESTAMPTZ,
    rejected_by        BIGINT REFERENCES users(id) ON DELETE SET NULL,
    rejected_at        TIMESTAMPTZ,
    rejection_reason   TEXT,
    executed_at        TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    expires_at         TIMESTAMPTZ,
    resulting_pipeline_id BIGINT REFERENCES pipelines(id) ON DELETE SET NULL,
    outcome_success    BOOLEAN,                  -- did the retried pipeline actually go green?
    audit              JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Default policy seed** (insert for every new team):

| action_type | mode | max_risk | min_confidence |
|---|---|---|---|
| `retry_job` | auto | low | 0.85 |
| `retry_pipeline` | approval | low | 0.85 |
| `create_issue` | auto | low | 0.70 |
| `investigate` | auto | low | 0.00 |
| `create_merge_request` | approval | medium | 0.90 |
| `edit_file` | approval | medium | 0.90 |
| `update_dependency` | approval | medium | 0.90 |
| `update_config` | approval | high | 0.95 |
| `rollback_deployment` | forbidden | critical | 1.00 |

`outcome_success` closes the loop: a remediation that ran and led to a green pipeline is evidence the resolution works, and promotes the signature to `is_known`.

---

## Group 6 — Vectors & knowledge

```sql
-- ready
CREATE TABLE failure_embeddings (
    id            BIGSERIAL PRIMARY KEY,
    failure_id    BIGINT NOT NULL REFERENCES failures(id) ON DELETE CASCADE,
    signature_id  BIGINT REFERENCES failure_signatures(id) ON DELETE CASCADE,
    team_id       BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    embedding     vector(384) NOT NULL,
    model         VARCHAR(120) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    dimensions    SMALLINT NOT NULL DEFAULT 384,
    source_text   TEXT NOT NULL,        -- exactly what was embedded (reproducibility)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (failure_id, model)
);

CREATE TABLE knowledge_documents (
    id            BIGSERIAL PRIMARY KEY,
    uuid          UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id       BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id    BIGINT REFERENCES projects(id) ON DELETE CASCADE,   -- NULL = team-wide
    type          VARCHAR(24) NOT NULL
                  CHECK (type IN ('runbook','readme','ci_config','incident',
                                  'resolution','doc','faq')),
    title         VARCHAR(255) NOT NULL,
    source_url    VARCHAR(500),
    source_path   VARCHAR(500),
    content       TEXT NOT NULL,
    content_hash  CHAR(64) NOT NULL,
    token_count   INTEGER,
    version       SMALLINT NOT NULL DEFAULT 1,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    indexed_at    TIMESTAMPTZ,
    created_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_chunks (
    id            BIGSERIAL PRIMARY KEY,
    document_id   BIGINT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    team_id       BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    chunk_index   SMALLINT NOT NULL,
    content       TEXT NOT NULL,
    token_count   SMALLINT,
    embedding     vector(384) NOT NULL,
    model         VARCHAR(120) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);
```

> **Changing the embedding model later:** the `model` column plus `UNIQUE(failure_id, model)` lets you backfill a second model alongside the first, compare retrieval quality on the same holdout set, and cut over. No migration, no data loss. Do not remove that column.

---

## Group 7 — Metrics, baselines, anomalies

```sql
-- ready
-- Nightly rollup. Powers every chart on the project board without scanning pipelines.
CREATE TABLE project_metrics_daily (
    id                    BIGSERIAL PRIMARY KEY,
    project_id            BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    team_id               BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    date                  DATE NOT NULL,
    pipelines_total       INTEGER NOT NULL DEFAULT 0,
    pipelines_success     INTEGER NOT NULL DEFAULT 0,
    pipelines_failed      INTEGER NOT NULL DEFAULT 0,
    pipelines_canceled    INTEGER NOT NULL DEFAULT 0,
    pipelines_running     INTEGER NOT NULL DEFAULT 0,
    success_rate          NUMERIC(5,2) NOT NULL DEFAULT 0,
    avg_duration_seconds  INTEGER NOT NULL DEFAULT 0,
    p50_duration_seconds  INTEGER NOT NULL DEFAULT 0,
    p95_duration_seconds  INTEGER NOT NULL DEFAULT 0,
    failures_count        INTEGER NOT NULL DEFAULT 0,
    failures_resolved     INTEGER NOT NULL DEFAULT 0,
    mttr_seconds          INTEGER,
    -- category counts as {"DATABASE":3,"TEST":1} → drives the donut and the bar list
    failures_by_category  JSONB NOT NULL DEFAULT '{}'::jsonb,
    analyses_count        INTEGER NOT NULL DEFAULT 0,
    ai_cost_usd           NUMERIC(10,6) NOT NULL DEFAULT 0,
    anomalies_count       INTEGER NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, date)
);

-- "Normal" per job, per branch. A 10-minute build is fine for one project and alarming for another.
CREATE TABLE job_baselines (
    id                    BIGSERIAL PRIMARY KEY,
    project_id            BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_name              VARCHAR(190) NOT NULL,
    ref                   VARCHAR(255) NOT NULL DEFAULT '*',
    sample_count          INTEGER NOT NULL DEFAULT 0,
    window_days           SMALLINT NOT NULL DEFAULT 30,
    mean_duration_seconds NUMERIC(10,2),
    stddev_duration       NUMERIC(10,2),
    median_duration_seconds NUMERIC(10,2),
    mad_duration          NUMERIC(10,2),        -- median abs deviation: robust to outliers
    p95_duration_seconds  NUMERIC(10,2),
    mean_memory_mb        NUMERIC(10,2),
    failure_rate          NUMERIC(5,4) NOT NULL DEFAULT 0,
    retry_rate            NUMERIC(5,4) NOT NULL DEFAULT 0,
    last_computed_at      TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, job_name, ref)
);

CREATE TABLE anomalies (
    id                BIGSERIAL PRIMARY KEY,
    uuid              UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id           BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id        BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    pipeline_id       BIGINT REFERENCES pipelines(id) ON DELETE CASCADE,
    job_id            BIGINT REFERENCES pipeline_jobs(id) ON DELETE CASCADE,
    type              VARCHAR(24) NOT NULL
                      CHECK (type IN ('duration','memory','failure_rate','retry_rate',
                                      'queue_time','test_count','log_size','flaky_test')),
    severity          VARCHAR(10) NOT NULL DEFAULT 'medium'
                      CHECK (severity IN ('low','medium','high','critical')),
    metric_name       VARCHAR(80) NOT NULL,
    observed_value    NUMERIC(14,4) NOT NULL,
    baseline_value    NUMERIC(14,4) NOT NULL,
    deviation_ratio   NUMERIC(8,3),        -- 4.1 → "4.1× higher than normal"
    z_score           NUMERIC(8,3),
    detection_method  VARCHAR(24) NOT NULL DEFAULT 'zscore'
                      CHECK (detection_method IN ('zscore','mad','iqr','isolation_forest','rule')),
    title             VARCHAR(255) NOT NULL,
    description       TEXT,
    possible_causes   JSONB NOT NULL DEFAULT '[]'::jsonb,
    status            VARCHAR(20) NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','acknowledged','resolved','false_positive')),
    acknowledged_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    acknowledged_at   TIMESTAMPTZ,
    detected_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Group 8 — AI providers, cost, notifications, activity

```sql
-- ready
CREATE TABLE ai_providers (
    id                BIGSERIAL PRIMARY KEY,
    uuid              UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id           BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name              VARCHAR(120) NOT NULL,
    provider          VARCHAR(30) NOT NULL
                      CHECK (provider IN ('gemini','openai','anthropic','ollama',
                                          'openai_compatible','azure_openai')),
    model             VARCHAR(120) NOT NULL,
    base_url          VARCHAR(255),
    api_key           TEXT,                    -- Laravel 'encrypted' cast; never returned by API
    is_default        BOOLEAN NOT NULL DEFAULT FALSE,
    is_local          BOOLEAN NOT NULL DEFAULT FALSE,   -- true → logs never leave infra
    max_tokens        INTEGER NOT NULL DEFAULT 4096,
    temperature       NUMERIC(3,2) NOT NULL DEFAULT 0.20,
    input_cost_per_1k  NUMERIC(10,6) NOT NULL DEFAULT 0,
    output_cost_per_1k NUMERIC(10,6) NOT NULL DEFAULT 0,
    status            VARCHAR(20) NOT NULL DEFAULT 'untested'
                      CHECK (status IN ('untested','active','error','disabled')),
    last_tested_at    TIMESTAMPTZ,
    last_error        TEXT,
    settings          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE projects
  ADD CONSTRAINT projects_ai_provider_fk
  FOREIGN KEY (ai_provider_id) REFERENCES ai_providers(id) ON DELETE SET NULL;

ALTER TABLE projects
  ADD CONSTRAINT projects_last_pipeline_fk
  FOREIGN KEY (last_pipeline_id) REFERENCES pipelines(id) ON DELETE SET NULL;

-- Every model call, billed or not. Budget enforcement + the cost chapter of your report.
CREATE TABLE ai_requests (
    id                BIGSERIAL PRIMARY KEY,
    uuid              UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id           BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id        BIGINT REFERENCES projects(id) ON DELETE SET NULL,
    failure_id        BIGINT REFERENCES failures(id) ON DELETE SET NULL,
    analysis_id       BIGINT REFERENCES analyses(id) ON DELETE SET NULL,
    ai_provider_id    BIGINT REFERENCES ai_providers(id) ON DELETE SET NULL,
    operation         VARCHAR(24) NOT NULL
                      CHECK (operation IN ('analyze','classify','embed','similar',
                                           'recommend','chat','summarize','patch')),
    provider          VARCHAR(30) NOT NULL,
    model             VARCHAR(120) NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms        INTEGER,
    cache_hit         BOOLEAN NOT NULL DEFAULT FALSE,
    status            VARCHAR(20) NOT NULL DEFAULT 'success'
                      CHECK (status IN ('success','error','timeout','rate_limited','budget_exceeded')),
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notification_channels (
    id            BIGSERIAL PRIMARY KEY,
    uuid          UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id       BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id    BIGINT REFERENCES projects(id) ON DELETE CASCADE,  -- NULL = all projects
    type          VARCHAR(20) NOT NULL
                  CHECK (type IN ('slack','teams','email','webhook','discord')),
    name          VARCHAR(120) NOT NULL,
    config        TEXT NOT NULL,                 -- encrypted: webhook url, channel, recipients
    events        JSONB NOT NULL DEFAULT '["failure.detected","analysis.completed"]'::jsonb,
    min_severity  VARCHAR(10) NOT NULL DEFAULT 'medium',
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    last_sent_at  TIMESTAMPTZ,
    last_error    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Laravel's standard notifications table (in-app bell, badge count).
CREATE TABLE notifications (
    id              UUID PRIMARY KEY,
    type            VARCHAR(255) NOT NULL,
    notifiable_type VARCHAR(255) NOT NULL,
    notifiable_id   BIGINT NOT NULL,
    data            JSONB NOT NULL,
    read_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Powers the "Recent Activity" feed on both target pages.
CREATE TABLE activity_logs (
    id            BIGSERIAL PRIMARY KEY,
    uuid          UUID NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    team_id       BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id    BIGINT REFERENCES projects(id) ON DELETE CASCADE,
    user_id       BIGINT REFERENCES users(id) ON DELETE SET NULL,
    actor_type    VARCHAR(10) NOT NULL DEFAULT 'user'
                  CHECK (actor_type IN ('user','system','ai','provider')),
    action        VARCHAR(60) NOT NULL,        -- pipeline.failed, analysis.completed, …
    level         VARCHAR(10) NOT NULL DEFAULT 'info'
                  CHECK (level IN ('info','success','warning','error')),
    title         VARCHAR(255) NOT NULL,
    description   TEXT,
    subject_type  VARCHAR(60),
    subject_id    BIGINT,
    subject_uuid  UUID,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Activity `action` vocabulary** (fixed list — the frontend maps each to an icon and color):

```text
pipeline.started     pipeline.succeeded    pipeline.failed      pipeline.canceled
job.failed           job.retried
failure.detected     failure.resolved      failure.ignored
analysis.started     analysis.completed    analysis.failed
anomaly.detected     anomaly.acknowledged
remediation.requested  remediation.approved  remediation.rejected
remediation.executed   remediation.succeeded remediation.failed
project.created      project.updated       integration.connected  integration.error
member.invited       member.joined
```

---

## Indexes

Everything below is load-bearing. Missing any of these turns a 20 ms page into a 4 s page once you have real data.

```sql
-- ready
-- tenancy & lookup
CREATE INDEX idx_team_user_user           ON team_user(user_id);
CREATE INDEX idx_integrations_team        ON integrations(team_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_projects_team_active     ON projects(team_id, is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_projects_uuid            ON projects(uuid);
CREATE INDEX idx_projects_last_pipeline   ON projects(last_pipeline_at DESC NULLS LAST);

-- pipeline lists (project board "Recent Pipelines", pagination)
CREATE INDEX idx_pipelines_project_created ON pipelines(project_id, created_at DESC);
CREATE INDEX idx_pipelines_project_status  ON pipelines(project_id, status);
CREATE INDEX idx_pipelines_ref             ON pipelines(project_id, ref);
CREATE INDEX idx_pipelines_commit          ON pipelines(commit_sha);
CREATE INDEX idx_pipelines_running         ON pipelines(status) WHERE status IN ('queued','running');
CREATE INDEX idx_pipelines_finished        ON pipelines(project_id, finished_at DESC)
                                              WHERE finished_at IS NOT NULL;

-- jobs
CREATE INDEX idx_jobs_pipeline            ON pipeline_jobs(pipeline_id, position);
CREATE INDEX idx_jobs_failed              ON pipeline_jobs(status) WHERE status = 'failed';
CREATE INDEX idx_jobs_name_duration       ON pipeline_jobs(name, duration_seconds)
                                              WHERE status = 'success';   -- baseline computation

-- events (idempotency + replay)
CREATE INDEX idx_events_pending           ON pipeline_events(processing_status, received_at)
                                              WHERE processing_status IN ('pending','failed');
CREATE INDEX idx_events_project_received  ON pipeline_events(project_id, received_at DESC);

-- failures (the failure list + MTTR)
CREATE INDEX idx_failures_project_failed  ON failures(project_id, failed_at DESC);
CREATE INDEX idx_failures_team_status     ON failures(team_id, status);
CREATE INDEX idx_failures_signature       ON failures(signature_id, failed_at DESC);
CREATE INDEX idx_failures_category        ON failures(project_id, category, failed_at DESC);
CREATE INDEX idx_failures_unresolved      ON failures(project_id, failed_at DESC)
                                              WHERE resolved_at IS NULL;
CREATE INDEX idx_signatures_team_hash     ON failure_signatures(team_id, hash);
CREATE INDEX idx_signatures_known         ON failure_signatures(team_id, is_known)
                                              WHERE is_known = TRUE;
-- fuzzy search over error text (⌘K global search)
CREATE INDEX idx_signatures_trgm          ON failure_signatures USING gin (sample_error gin_trgm_ops);

-- analyses
CREATE INDEX idx_analyses_failure         ON analyses(failure_id, created_at DESC);
CREATE INDEX idx_analyses_team_created    ON analyses(team_id, created_at DESC);
CREATE INDEX idx_evidence_analysis        ON analysis_evidence(analysis_id, position);
CREATE INDEX idx_recos_failure            ON recommendations(failure_id, position);
CREATE INDEX idx_recos_status             ON recommendations(status) WHERE status = 'proposed';

-- remediation
CREATE INDEX idx_remediations_pending     ON remediations(team_id, status)
                                              WHERE status = 'pending_approval';
CREATE INDEX idx_remediations_project     ON remediations(project_id, created_at DESC);

-- vectors: HNSW beats IVFFlat for our size and needs no training step
CREATE INDEX idx_failure_embeddings_hnsw  ON failure_embeddings
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_failure_embeddings_team  ON failure_embeddings(team_id);
CREATE INDEX idx_knowledge_chunks_hnsw    ON knowledge_chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_knowledge_chunks_team    ON knowledge_chunks(team_id);

-- metrics & anomalies
CREATE INDEX idx_metrics_project_date     ON project_metrics_daily(project_id, date DESC);
CREATE INDEX idx_anomalies_project_open   ON anomalies(project_id, detected_at DESC)
                                              WHERE status = 'open';

-- cost
-- This composite alone serves the month-to-date budget query
--   WHERE team_id = ? AND created_at >= date_trunc('month', now())
-- as a range scan. Do NOT add a date_trunc() expression index: it is redundant,
-- and PostgreSQL rejects it because date_trunc() on timestamptz is STABLE rather
-- than IMMUTABLE (its result depends on the session TimeZone).
CREATE INDEX idx_ai_requests_team_created ON ai_requests(team_id, created_at DESC);

-- activity feed (both target pages)
CREATE INDEX idx_activity_team_created    ON activity_logs(team_id, created_at DESC);
CREATE INDEX idx_activity_project_created ON activity_logs(project_id, created_at DESC);

-- notifications bell
CREATE INDEX idx_notifications_unread     ON notifications(notifiable_id, read_at)
                                              WHERE read_at IS NULL;
```

---

## Cardinality & growth

| Table | Rows per pipeline | Growth | Retention |
|---|---|---|---|
| `pipelines` | 1 | linear | keep |
| `pipeline_jobs` | 5–30 | linear ×20 | keep |
| `pipeline_events` | 3–40 | **fastest** | prune > 30 days |
| `job_logs` (metadata) | 0–5 (failed jobs only) | slow | keep; object bytes lifecycle after 90 days |
| `commit_changes` | 0–200 | medium | prune > 90 days |
| `failures` | 0–3 | slow | keep forever — this is the knowledge base |
| `analyses` | 0–3 | slow | keep forever |
| `failure_embeddings` | 0–3 | slow | keep forever |
| `ai_requests` | 0–6 | medium | prune > 180 days after rollup |
| `activity_logs` | 3–10 | fast | prune > 90 days |

- [ ] Add a `PruneOldRecords` scheduled command in file 03 covering the prune rows above

---

## Migration order

Foreign keys force this sequence. Prefix Laravel migrations with timestamps in exactly this order:

```text
 1 users                     12 commit_changes           23 knowledge_chunks
 2 teams                     13 failure_signatures       24 project_metrics_daily
 3 (users.current_team_id FK)14 failures                 25 job_baselines
 4 team_user                 15 analyses                 26 anomalies
 5 team_invitations          16 analysis_evidence        27 ai_providers
 6 integrations              17 recommendations          28 (projects FKs: ai_provider, last_pipeline)
 7 projects                  18 analysis_feedback        29 ai_requests
 8 pipelines                 19 remediation_policies     30 notification_channels
 9 pipeline_stages           20 remediations             31 notifications
10 pipeline_jobs             21 failure_embeddings       32 activity_logs
11 pipeline_events           22 knowledge_documents      33 job_logs
```

> `job_logs` goes last because it references three tables. `projects` FKs to `ai_providers` and `pipelines` are added in a separate late migration to break the circular dependency.

---

## Tasks

- [ ] Write this schema to `PipeMind-data/database/schema.sql` (concatenate all DDL above, in migration order)
- [ ] Generate the ERD → `PipeMind-data/database/diagrams/erd.png` (paste `schema.sql` into dbdiagram.io, or use `mermerd`)
- [ ] Commit the Mermaid/DBML source next to the PNG so it stays editable
- [ ] Write one `PipeMind-data/database/schema/<group>.md` per group: purpose, key columns, why each denormalisation exists
- [ ] Write `PipeMind-data/taxonomy/failure-categories.md` — the 13 categories with subcategories and 3 example log lines each
- [ ] Validate: `docker exec -i pipemind-postgres psql -U pipemind -d pipemind < database/schema.sql` runs clean on an empty DB

## Definition of Done

```bash
docker exec pipemind-postgres psql -U pipemind -d pipemind -c "\dt" | wc -l   # ≥ 31 tables
docker exec pipemind-postgres psql -U pipemind -d pipemind -c \
  "SELECT count(*) FROM pg_indexes WHERE schemaname='public';"                # ≥ 45 indexes
docker exec pipemind-postgres psql -U pipemind -d pipemind -c \
  "SELECT indexname FROM pg_indexes WHERE indexdef LIKE '%hnsw%';"            # 2 vector indexes
```

Then **drop it all again** — Laravel owns the real migrations:
```bash
docker exec pipemind-postgres psql -U pipemind -d pipemind -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker exec pipemind-postgres psql -U pipemind -d pipemind -f /docker-entrypoint-initdb.d/01-extensions.sql
```

The `schema.sql` in `PipeMind-data` is documentation and validation. `PipeMind-back/database/migrations` is the implementation. They must never diverge — file 03 adds a CI check for that.

**Next:** [`03-backend-setup.md`](03-backend-setup.md)
