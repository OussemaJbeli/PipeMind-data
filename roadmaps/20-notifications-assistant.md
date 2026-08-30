# 20 — Notifications, Search & Assistant

**Repo:** all · **Depends on:** 19 · **Milestone:** M5

Getting PipeMind out of the browser tab and into the places developers already are — plus ⌘K search and the conversational assistant.

---

## 20.1 Notification channels

```php
// ready — app/Notifications/FailureAnalyzed.php
class FailureAnalyzed extends Notification implements ShouldQueue
{
    use Queueable;

    public function __construct(public Failure $failure) {}

    public function via(object $notifiable): array
    {
        return ['database', 'broadcast'];   // channels resolve separately per team config
    }

    public function toSlack(NotificationChannel $channel): array
    {
        $a = $this->failure->latestAnalysis;

        return [
            'blocks' => [
                ['type' => 'header', 'text' => ['type' => 'plain_text',
                    'text' => "❌ {$this->failure->project->name} · Pipeline #{$this->failure->pipeline->iid}"]],

                ['type' => 'section', 'fields' => [
                    ['type' => 'mrkdwn', 'text' => "*Category*\n{$a->category}"],
                    ['type' => 'mrkdwn', 'text' => "*Confidence*\n".round($a->confidence * 100).'%'],
                    ['type' => 'mrkdwn', 'text' => "*Branch*\n`{$this->failure->pipeline->ref}`"],
                    ['type' => 'mrkdwn', 'text' => "*Job*\n{$this->failure->job_name}"],
                ]],

                ['type' => 'section', 'text' => ['type' => 'mrkdwn',
                    'text' => "*Root cause*\n{$a->root_cause}"]],

                // One decisive line beats a wall of detail. The link carries the rest.
                ...($this->failure->similar_failures_count ? [[
                    'type' => 'context',
                    'elements' => [['type' => 'mrkdwn',
                        'text' => "🔁 Similar to a past failure that was resolved"]],
                ]] : []),

                ['type' => 'actions', 'elements' => [
                    ['type' => 'button', 'style' => 'primary',
                     'text' => ['type' => 'plain_text', 'text' => 'View analysis'],
                     'url' => $this->failureUrl()],
                    ['type' => 'button',
                     'text' => ['type' => 'plain_text', 'text' => 'Open in GitLab'],
                     'url' => $this->failure->pipeline->web_url],
                ]],
            ],
        ];
    }
}
```

**Notification policy — the difference between useful and muted:**

| Rule | Why |
|---|---|
| Notify on `analysis.completed`, not `failure.detected` | A notification saying "it broke" adds nothing over the CI platform's own. One saying *why* is worth reading. |
| Respect `min_severity` per channel | Low-severity feature-branch noise should not reach a shared channel. |
| Deduplicate by signature within 1 hour | The same broken dependency failing six pipelines is one message, with a count. |
| Never notify for flaky failures | By definition not actionable. |
| Digest mode for high-volume projects | Hourly rollup instead of per-failure. |
| Never include log content | It may contain something redaction missed; the link is safer than the excerpt. |

> **The last rule is a genuine safety boundary.** Redaction is very good, not perfect. A Slack channel is often wider than the PipeMind workspace and is indexed and retained. Send the link; let authorisation do its job on the other end.

- [ ] `NotificationChannel` dispatcher: Slack, Teams, email, generic webhook
- [ ] Dedupe by signature, digest mode, severity filter
- [ ] Test-send button per channel
- [ ] Per-user preferences (all / mentions / none)

---

## 20.2 Global search — ⌘K

```php
// ready — GET /api/v1/search?q=
// Searches, in priority order:
//   1. exact pipeline iid  (#821 or 821)
//   2. commit sha prefix
//   3. project name (trigram)
//   4. failure signature sample_error (trigram — idx_signatures_trgm from file 02)
//   5. job names
// Returns typed results with a route and an icon. Limit 8 per type.
```

```text
┌─ ⌘K ────────────────────────────────────────────────┐
│ 🔍 connection refused                               │
├─────────────────────────────────────────────────────┤
│ FAILURES                                            │
│ ⚠ DATABASE · Connection refused      biker-api   12×│
│ ⚠ DOCKER · daemon connection refused biker-mobile 2×│
│ PROJECTS                                            │
│ ▣ biker-api                                         │
│ ACTIONS                                             │
│ ↻ Retry pipeline #821                               │
│ → Go to Failures                                    │
└─────────────────────────────────────────────────────┘
```

Trigram search over `sample_error` is what makes "I remember seeing this error" actually work — and the index already exists from file 02.

- [ ] `SearchController` + `CommandPalette` component
- [ ] Debounced 200 ms, keyboard-navigable, recent searches in `localStorage`

---

## 20.3 AI Assistant

Conversational access to the same data and analysis layer. **Not** a general chatbot.

```python
# spec — POST /v1/chat  (PipeMind-ai)
# Tools available to the model — all read-only, all going through Laravel:
#   get_pipeline(iid)            get_failure(uuid)
#   search_failures(query, range) get_project_metrics(range)
#   find_similar(error_text)      get_job_log_excerpt(job_uuid)
#   list_anomalies(status)
#
# The assistant NEVER executes remediation. If asked to "retry #821" it returns
# a proposed action the UI renders as a confirmation card, which then goes
# through the normal policy + approval path from file 18.
```

```text
┌─ Ask PipeMind ──────────────────────────────────────┐
│ You: why did BO-12 fail?                            │
│                                                     │
│ PipeMind:                                           │
│ Pipeline #821 on feature/payment failed in the test │
│ stage. The integration tests could not reach the    │
│ database — docker-compose.yml lost its healthcheck  │
│ dependency in this commit.                          │
│                                                     │
│ [ Failure #4821 ]  92% confidence                   │
│                                                     │
│ This has happened 4 times. The last fix was adding  │
│ a healthcheck-based depends_on.                     │
│                                                     │
│ ⟳ Retry pipeline #821?  [Yes, request it] [No]      │
└─────────────────────────────────────────────────────┘
```

**Assistant rules:**

1. Every factual claim comes from a tool call, never from model memory. Cite the entity.
2. Scope every tool call to the current team — the same tenancy boundary as the API.
3. Stream via SSE; show tool calls as they happen ("Looking up pipeline #821…") so latency is legible.
4. Rate-limit per user (`assistant`, 30/hour) and count against the team's AI budget.
5. Actions are *proposals* rendered as cards. The assistant cannot approve anything.

> **The assistant is a different interface to the same intelligence, not a second brain.** If it answers from the model's general knowledge instead of your data, it will confidently describe a pipeline you don't have. Tool-grounded or silent.

- [ ] `/v1/chat` with tool calling + SSE streaming
- [ ] `AssistantDrawer` component, openable from anywhere
- [ ] Conversation history persisted per user
- [ ] Feature-flagged (`VITE_ENABLE_ASSISTANT`) — ship it last

---

## Definition of Done

- [ ] A real failure posts a Slack message with root cause and a working link
- [ ] Six pipelines failing on one signature produce one message, not six
- [ ] ⌘K finds a pipeline by `#iid`, a project by name, a failure by error text
- [ ] The assistant answers "why did #821 fail" using tool calls, with a citation
- [ ] Asking it to retry produces a confirmation card, not an execution
- [ ] Assistant usage appears in `ai_requests` and counts against the budget

**Next:** [`21-testing-quality.md`](21-testing-quality.md)
