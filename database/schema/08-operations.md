# Group 8 — Operations

`ai_providers` · `ai_requests` · `notification_channels` · `notifications` · `activity_logs`

## `ai_providers`

Per-team LLM configuration. Supports `gemini`, `openai`, `anthropic`, `ollama`,
`openai_compatible`, `azure_openai`, and `stub`.

**Pricing lives in the row, not in code** (`input_cost_per_1k` / `output_cost_per_1k`).
Rates change; a hardcoded number becomes a lie in a month. Fill each row from the
provider's current pricing page and record when you checked.

**`is_local`** marks providers where logs never leave your infrastructure. A team with
`privacy_mode = local_only` can only use these.

**`api_key`** is `encrypted` cast and in `$hidden`. It is passed per-request to the AI
service as an override, so the AI service stores no team's credentials at rest.

## `ai_requests`

Every model call, billed or not — including cache hits at `cost_usd = 0` and failures.

This table answers: what did this cost, where did the time go, how often did the cache
save us, and how often did we actually need the LLM. Every one of those numbers belongs
in the report.

The month-to-date budget query is a range scan on `(team_id, created_at DESC)`:

```sql
WHERE team_id = ? AND created_at >= date_trunc('month', now())
```

> Do **not** add a `date_trunc()` expression index for this. It is redundant, and
> PostgreSQL rejects it: `date_trunc()` on `timestamptz` is `STABLE`, not `IMMUTABLE`,
> because its result depends on the session TimeZone.

## `activity_logs`

Powers the "Recent Activity" feed on both target pages. The `action` vocabulary is a
fixed list — the frontend maps each to an icon and colour, and degrades unknown actions
to a neutral dot rather than crashing, so the backend can add actions safely.

Fastest-growing table after `pipeline_events`. Prune after 90 days.

## `notification_channels`

Slack, Teams, email, webhook, Discord. `config` is encrypted (webhook URLs are
credentials).

**Notifications carry a link, never log content.** Redaction is very good, not perfect,
and a Slack channel is usually wider than the PipeMind workspace, indexed and retained.
The link lets authorisation do its job on the other end.
