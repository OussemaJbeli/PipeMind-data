# PipeMind — Entity Relationship Diagram

Renders natively on GitHub. Source: [`erd.mmd`](erd.mmd) · Authoritative schema: [`../schema.sql`](../schema.sql)

To export a PNG for the report:

```bash
npx -y @mermaid-js/mermaid-cli -i erd.mmd -o erd.png -t dark -b "#0A0B0E" -w 2400
```

```mermaid
%% PipeMind — Entity Relationship Diagram
%% Source of truth: ../schema.sql
%% Render: mmdc -i erd.mmd -o erd.png -t dark -b '#0A0B0E' -w 2400

erDiagram
    users             ||--o{ team_user            : "belongs to"
    teams             ||--o{ team_user            : "has members"
    teams             ||--o{ team_invitations     : "invites"
    teams             ||--o{ integrations         : "connects"
    teams             ||--o{ projects             : "owns"
    teams             ||--o{ ai_providers         : "configures"
    teams             ||--o{ remediation_policies : "governs"
    teams             ||--o{ notification_channels: "notifies via"
    teams             ||--o{ failure_signatures   : "catalogues"
    teams             ||--o{ knowledge_documents  : "knows"
    teams             ||--o{ activity_logs        : "records"
    teams             ||--o{ ai_requests          : "spends"

    integrations      ||--o{ projects             : "provides"
    integrations      ||--o{ pipeline_events      : "delivers"

    projects          ||--o{ pipelines            : "runs"
    projects          ||--o{ failures             : "suffers"
    projects          ||--o{ anomalies            : "exhibits"
    projects          ||--o{ project_metrics_daily: "rolls up"
    projects          ||--o{ job_baselines        : "baselines"
    projects          ||--o{ knowledge_documents  : "documents"
    ai_providers      ||--o{ projects             : "analyses for"

    pipelines         ||--o{ pipeline_stages      : "has"
    pipelines         ||--o{ pipeline_jobs        : "has"
    pipelines         ||--o{ commit_changes       : "changed"
    pipelines         ||--o{ pipeline_events      : "raised"
    pipelines         ||--o{ failures             : "produced"
    pipeline_stages   ||--o{ pipeline_jobs        : "groups"
    pipeline_jobs     ||--|| job_logs             : "wrote"
    pipeline_jobs     ||--o| failures             : "failed with"

    failure_signatures ||--o{ failures            : "dedupes"
    failure_signatures ||--o{ failure_embeddings  : "vectorises"

    failures          ||--o{ analyses             : "analysed by"
    failures          ||--|| failure_embeddings   : "embedded as"
    failures          ||--o{ recommendations      : "suggests"
    failures          ||--o{ remediations         : "remediated by"

    analyses          ||--o{ analysis_evidence    : "cites"
    analyses          ||--o{ recommendations      : "proposes"
    analyses          ||--o{ analysis_feedback    : "rated by"

    recommendations   ||--o| remediations         : "becomes"
    remediation_policies ||..o{ remediations      : "gates"
    remediations      }o--o| pipelines            : "triggers"

    knowledge_documents ||--o{ knowledge_chunks   : "chunked into"

    users             ||--o{ analysis_feedback    : "gives"
    users             ||--o{ remediations         : "approves"

    users {
        bigint id PK
        uuid uuid UK
        string email UK
        bigint current_team_id FK
    }
    teams {
        bigint id PK
        uuid uuid UK
        string slug UK
        string privacy_mode "cloud_redacted|local_only"
        numeric monthly_ai_budget_usd
    }
    projects {
        bigint id PK
        uuid uuid UK
        bigint team_id FK
        jsonb tech_stack
        numeric success_rate "denormalised"
        int failures_today "denormalised"
        string health_status
    }
    pipelines {
        bigint id PK
        uuid uuid UK
        string external_id UK "unique per project"
        int iid "display number"
        string status
        string ref
        string commit_sha
    }
    pipeline_jobs {
        bigint id PK
        string status
        smallint exit_code
        int duration_seconds
        int peak_memory_mb
    }
    job_logs {
        bigint job_id PK_FK
        string storage_path "MinIO key"
        bool is_redacted
        text excerpt "what the LLM sees"
        text error_block
    }
    failure_signatures {
        bigint id PK
        char hash UK "sha256, unique per team"
        text normalized_error
        bool is_known
        text known_resolution
    }
    failures {
        bigint id PK
        uuid uuid UK
        string category
        string severity
        bool is_flaky
        int occurrence_index
        int time_to_resolution_seconds
    }
    analyses {
        bigint id PK
        numeric confidence "0..1"
        text root_cause
        string classification_source "rules|ml|llm|hybrid"
        bool used_rag
        numeric cost_usd
        bool cache_hit
    }
    analysis_evidence {
        bigint id PK
        string type
        string source_ref "job_logs#L1294"
        numeric weight
    }
    recommendations {
        bigint id PK
        string action_type
        string risk "assigned by code, never the model"
        text patch
    }
    remediations {
        bigint id PK
        string policy_decision
        string status
        bool outcome_success "closes the learning loop"
        jsonb audit
    }
    failure_embeddings {
        bigint id PK
        vector embedding "384, HNSW cosine"
        string model "allows side-by-side backfill"
    }
```
