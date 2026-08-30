# Schema Documentation

Per-group documentation of the PipeMind data model. Authoritative DDL: [`../schema.sql`](../schema.sql).
Diagram: [`../diagrams/erd.md`](../diagrams/erd.md).

| File | Tables | Purpose |
|---|---|---|
| [`00-decisions.md`](00-decisions.md) | — | Architecture decisions and host port allocation |
| [`01-identity.md`](01-identity.md) | 4 | Users, teams, membership, invitations |
| [`02-projects.md`](02-projects.md) | 2 | Integrations and projects |
| [`03-pipelines.md`](03-pipelines.md) | 6 | Pipelines, stages, jobs, events, logs, commit changes |
| [`04-failures.md`](04-failures.md) | 6 | Signatures, failures, analyses, evidence, recommendations, feedback |
| [`05-remediation.md`](05-remediation.md) | 2 | Policies and remediations |
| [`06-vectors.md`](06-vectors.md) | 3 | Embeddings and knowledge base |
| [`07-metrics.md`](07-metrics.md) | 3 | Daily rollups, baselines, anomalies |
| [`08-operations.md`](08-operations.md) | 5 | AI providers, cost, notifications, activity |

**Total: 31 tables.**

The goal: someone should understand the data model without reading the Laravel codebase.
