# 04 — Backend Auth & API

**Repo:** `PipeMind-back` · **Depends on:** 03 · **Milestone:** M1

Sanctum auth, team context, RBAC policies, and the complete REST surface. Every endpoint the frontend will ever call is defined here — including the exact payloads that render `ui/workspace.png` and `ui/project.png`.

---

## 4.1 Authentication

Sanctum **SPA cookie mode** for the browser, **bearer tokens** for the CLI and CI.

```php
// ready — bootstrap/app.php
->withMiddleware(function (Middleware $middleware) {
    $middleware->statefulApi();

    $middleware->api(prepend: [
        \Laravel\Sanctum\Http\Middleware\EnsureFrontendRequestsAreStateful::class,
    ]);

    $middleware->alias([
        'team'      => \App\Http\Middleware\ResolveTeam::class,
        'team.role' => \App\Http\Middleware\EnsureTeamRole::class,
    ]);

    $middleware->throttleApi('api');
})
```

```php
// ready — app/Http/Middleware/ResolveTeam.php
public function handle(Request $request, Closure $next): Response
{
    $user = $request->user();

    // Explicit header wins (lets the frontend switch workspace without a round trip)
    $uuid = $request->header('X-Team');
    $team = $uuid
        ? $user->teams()->where('teams.uuid', $uuid)->first()
        : $user->currentTeam;

    abort_if(! $team, 403, 'No accessible team for this request.');

    app()->instance('pipemind.team', $team);
    $request->attributes->set('team', $team);

    return $next($request);
}
```

```php
// ready — app/Http/Middleware/EnsureTeamRole.php  — usage: ->middleware('team.role:owner,admin')
public function handle(Request $request, Closure $next, string ...$roles): Response
{
    $role = currentTeam()?->users()
        ->where('users.id', $request->user()->id)
        ->value('team_user.role');

    abort_unless($role && in_array($role, $roles, true), 403, 'Insufficient team role.');

    return $next($request);
}
```

**Rate limits** (`AppServiceProvider::boot`):

| Limiter | Limit | Applies to |
|---|---|---|
| `api` | 120/min per user | all authenticated API |
| `auth` | 5/min per IP | login, register, forgot-password |
| `webhooks` | 600/min per integration | webhook ingress |
| `analysis` | 20/hour per team | manual "Analyze" trigger |
| `assistant` | 30/hour per user | AI chat |

- [ ] Middleware written and registered
- [ ] Rate limiters defined
- [ ] CORS configured for `FRONTEND_URL` with `supports_credentials => true`

---

## 4.2 Endpoint reference

Base: `/api/v1`. All authenticated routes require Sanctum + `team` middleware unless noted.
Column **Role** = minimum team role.

### Auth — `routes/api.php`, no team middleware

| Method | Path | Role | Body / Notes |
|---|---|---|---|
| POST | `/auth/register` | — | `name, email, password, password_confirmation, team_name?` → creates user + personal team |
| POST | `/auth/login` | — | `email, password, remember?` |
| POST | `/auth/logout` | auth | — |
| GET | `/auth/me` | auth | user + teams + current team + role + permissions |
| PUT | `/auth/profile` | auth | `name, job_title, timezone, theme, avatar` |
| PUT | `/auth/password` | auth | `current_password, password, password_confirmation` |
| POST | `/auth/forgot-password` | — | `email` |
| POST | `/auth/reset-password` | — | `token, email, password` |
| POST | `/auth/email/resend` | auth | — |
| GET | `/auth/email/verify/{id}/{hash}` | signed | — |
| POST | `/auth/tokens` | auth | create a CLI/CI bearer token — returns plaintext **once** |
| GET | `/auth/tokens` | auth | list token names + last_used_at |
| DELETE | `/auth/tokens/{id}` | auth | revoke |

```jsonc
// GET /auth/me
{
  "data": {
    "uuid": "…", "name": "Oussema", "email": "PmAG01@evoxai.ca",
    "avatar_url": null, "initials": "OU", "theme": "dark",
    "timezone": "Africa/Tunis", "onboarded_at": "2026-08-30T09:12:00Z",
    "current_team": { "uuid": "…", "name": "Evox AI", "slug": "evox-ai", "role": "owner",
                      "plan": "free", "privacy_mode": "cloud_redacted" },
    "teams": [ { "uuid": "…", "name": "Evox AI", "role": "owner", "projects_count": 4 } ],
    "permissions": ["projects.manage","remediation.approve","team.manage","policies.edit"]
  }
}
```

> `permissions` is a flat string array derived from the role matrix in file 02. The frontend does `can('remediation.approve')` and never reimplements the role logic. One source of truth.

### Teams & members

| Method | Path | Role |
|---|---|---|
| GET | `/teams` | member |
| POST | `/teams` | auth |
| GET | `/teams/{team}` | viewer |
| PUT | `/teams/{team}` | admin |
| DELETE | `/teams/{team}` | owner |
| POST | `/teams/{team}/switch` | viewer |
| GET | `/teams/{team}/members` | viewer |
| PUT | `/teams/{team}/members/{user}` | admin — change role |
| DELETE | `/teams/{team}/members/{user}` | admin |
| GET | `/teams/{team}/invitations` | admin |
| POST | `/teams/{team}/invitations` | admin — `email, role` |
| DELETE | `/teams/{team}/invitations/{invitation}` | admin |
| POST | `/invitations/{token}/accept` | auth, no team mw |
| GET | `/teams/{team}/usage` | admin — AI spend vs budget |

### Workspace — powers `ui/workspace.png`

| Method | Path | Role |
|---|---|---|
| GET | `/workspace/summary` | viewer |
| GET | `/workspace/projects` | viewer |
| GET | `/workspace/activity?limit=10` | viewer |

```jsonc
// GET /workspace/summary  →  the four KPI tiles
{
  "data": {
    "projects":     { "value": 4,    "delta": 1,     "delta_label": "+1 this week",        "trend": "up" },
    "pipelines_today": { "value": 127, "delta": 18.7, "delta_label": "+18.7% vs yesterday","trend": "up" },
    "failures_today":  { "value": 3,   "delta": -25.0,"delta_label": "-25% vs yesterday",  "trend": "down", "positive_direction": "down" },
    "success_rate":    { "value": 96.3,"unit": "%",   "delta": 2.4, "delta_label": "+2.4% vs last week", "trend": "up" }
  }
}
```

> `positive_direction` tells the UI whether a downward arrow should be green or red. Fewer failures is good; fewer pipelines is neutral. Encode it server-side so no component has to know the semantics of each metric.

```jsonc
// GET /workspace/projects  →  the project cards
{
  "data": [
    {
      "uuid": "…", "name": "biker-api", "slug": "biker-api",
      "icon": "code", "color": "#6366F1",
      "tech_stack": ["Laravel","Docker","GitLab"],
      "health_status": "healthy",
      "success_rate": 98.0,
      "failures_today": 2,
      "pipelines_count": 124,
      "last_pipeline": {
        "iid": 821, "uuid": "…", "status": "success",
        "finished_at": "2026-08-30T14:32:10Z", "duration_seconds": 134
      }
    }
  ]
}
```

```jsonc
// GET /workspace/activity
{
  "data": [
    {
      "uuid": "…", "action": "pipeline.failed", "level": "error",
      "title": "biker-api", "description": "Pipeline #821 failed on step database:integration",
      "project": { "uuid": "…", "name": "biker-api", "slug": "biker-api" },
      "subject_type": "pipeline", "subject_uuid": "…",
      "created_at": "2026-08-30T14:32:10Z"
    }
  ]
}
```

### Projects — powers `ui/project.png`

| Method | Path | Role |
|---|---|---|
| GET | `/projects` | viewer — filter, sort, paginate |
| POST | `/projects` | admin |
| GET | `/projects/{project}` | viewer |
| PUT | `/projects/{project}` | admin |
| DELETE | `/projects/{project}` | admin |
| GET | `/projects/{project}/overview?range=7d` | viewer — **the board payload** |
| GET | `/projects/{project}/metrics?range=30d&granularity=daily` | viewer |
| GET | `/projects/{project}/failure-breakdown?range=7d` | viewer |
| GET | `/projects/{project}/activity?limit=10` | viewer |
| GET | `/projects/{project}/insights` | viewer — the AI Insight card |
| GET | `/projects/{project}/health` | viewer |
| POST | `/projects/{project}/sync` | admin — force provider resync |

```jsonc
// GET /projects/{project}/overview?range=7d   — one request, whole board
{
  "data": {
    "project": {
      "uuid":"…","name":"biker-api","slug":"biker-api","initials":"BA",
      "tech_stack":["Laravel","Docker","GitLab"],
      "provider":"gitlab","default_branch":"main","web_url":"http://gitlab.local/…"
    },

    // five KPI tiles, each with a sparkline series
    "kpis": {
      "pipeline_health": { "value":98.2,"unit":"%","delta":3.6,"trend":"up",
                           "spark":[96.1,97.0,96.4,98.2,97.8,98.9,98.2] },
      "pipelines":       { "value":127,"delta":18,"trend":"up",
                           "spark":[14,19,17,22,18,20,17] },
      "failures":        { "value":3,"delta":-5,"trend":"down","positive_direction":"down",
                           "spark":[2,1,0,3,1,0,3] },
      "avg_duration":    { "value":222,"unit":"s","display":"3m 42s","delta":-24,"trend":"down",
                           "positive_direction":"down","spark":[240,238,229,226,221,219,222] },
      "mttr":            { "value":1080,"unit":"s","display":"18m","delta":-420,"trend":"down",
                           "positive_direction":"down","spark":[1500,1440,1320,1200,1140,1080,1080] }
    },

    // "Pipeline Activity" multi-series line chart
    "activity_chart": {
      "granularity":"daily",
      "series": [
        { "key":"success","label":"Success","color":"#A9E831",
          "points":[{"x":"2026-05-12","y":72},{"x":"2026-05-13","y":68}] },
        { "key":"failed","label":"Failed","color":"#F04438","points":[] },
        { "key":"running","label":"Running","color":"#6366F1","points":[] }
      ]
    },

    // donut + legend
    "failure_breakdown": {
      "total": 3,
      "items": [
        { "category":"DATABASE","label":"Database","count":1,"percentage":33.3,"color":"#A9E831" },
        { "category":"TEST","label":"Tests","count":1,"percentage":33.3,"color":"#F04438" },
        { "category":"DEPENDENCY","label":"Dependencies","count":1,"percentage":33.3,"color":"#F5A524" },
        { "category":"OTHER","label":"Others","count":0,"percentage":0,"color":"#5C6472" }
      ]
    },

    // horizontal bar list
    "top_categories": [
      { "category":"DATABASE","label":"Database","count":1,"percentage":33.3,"color":"#A9E831" }
    ],

    // AI Insight card
    "insight": {
      "uuid":"…","type":"pattern",
      "headline":"Database readiness issues detected in 2 pipelines in the last 24h.",
      "detail":"This is 32% higher than your normal baseline.",
      "severity":"warning","confidence":0.87,
      "action": { "label":"Investigate","route":"failures","params":{"category":"DATABASE","range":"24h"} }
    },

    // "Recent Pipelines" table
    "recent_pipelines": [
      { "uuid":"…","iid":821,"status":"failed","ref":"feature/payment",
        "duration_seconds":134,"duration_display":"2m 14s",
        "finished_at":"2026-08-30T14:32:10Z","provider":"gitlab",
        "commit_short_sha":"a82c91","has_failure":true,"failure_uuid":"…" }
    ],

    // "Pipeline Success Rate" 30-day bar chart
    "success_rate_chart": {
      "value":98.2,"delta":3.6,"range":"30d",
      "bars":[{"date":"2026-04-20","success_rate":100,"total":18,"failed":0}]
    },

    "recent_activity": [ /* same shape as workspace activity */ ]
  }
}
```

> **One request, not eleven.** The board has eleven distinct data regions. Eleven round trips means eleven spinners and a page that assembles itself visibly. Compose server-side from `project_metrics_daily` — it is a handful of indexed reads against a rollup table, and it stays fast at any history depth.

### Integrations

| Method | Path | Role |
|---|---|---|
| GET | `/integrations` | admin |
| POST | `/integrations` | admin — `provider, name, base_url, token` |
| GET | `/integrations/{integration}` | admin |
| PUT | `/integrations/{integration}` | admin |
| DELETE | `/integrations/{integration}` | admin |
| POST | `/integrations/{integration}/test` | admin — verify creds, return identity + scopes |
| POST | `/integrations/{integration}/sync` | admin |
| GET | `/integrations/{integration}/remote-projects?search=` | admin — importable repos |
| POST | `/integrations/{integration}/import` | admin — `external_ids[]` → creates projects + registers webhooks |
| GET | `/integrations/{integration}/webhook-url` | admin — the URL to paste into the provider |

### Pipelines & jobs

| Method | Path | Role |
|---|---|---|
| GET | `/projects/{project}/pipelines` | viewer — `?status=&ref=&source=&from=&to=&page=&per_page=` |
| GET | `/pipelines/{pipeline}` | viewer — includes stages, jobs, changes, failures |
| GET | `/pipelines/{pipeline}/jobs` | viewer |
| GET | `/pipelines/{pipeline}/changes` | viewer |
| POST | `/pipelines/{pipeline}/retry` | member |
| POST | `/pipelines/{pipeline}/cancel` | member |
| GET | `/jobs/{job}` | viewer |
| GET | `/jobs/{job}/log?mode=excerpt\|full&format=json\|text` | viewer |
| GET | `/jobs/{job}/log/download` | viewer — signed temporary S3 URL |
| POST | `/jobs/{job}/retry` | member |

```jsonc
// GET /jobs/{job}/log?mode=excerpt
{
  "data": {
    "job_uuid":"…","size_bytes":2481920,"line_count":48219,
    "truncated":true,"is_redacted":true,"redaction_count":3,
    "redaction_types":["aws_key","bearer_token","db_password"],
    "excerpt_start_line":1281,"excerpt_end_line":1310,
    "lines":[
      {"n":1281,"text":"$ php artisan test --testsuite=Integration","level":"info"},
      {"n":1294,"text":"SQLSTATE[HY000] [2002] Connection refused","level":"error","highlight":true}
    ],
    "error_block":"SQLSTATE[HY000] [2002] Connection refused\n  at DatabaseTest.php:42",
    "stack_trace":"…",
    "full_url":"/api/v1/jobs/…/log?mode=full"
  }
}
```

> `highlight: true` marks the lines the log processor identified as the error. The frontend renders them with a left accent bar and scrolls to the first one on mount. This is the difference between "here are 48,219 lines" and "here is your problem."

### Failures & analyses

| Method | Path | Role |
|---|---|---|
| GET | `/projects/{project}/failures` | viewer — `?status=&category=&severity=&resolved=&range=` |
| GET | `/failures` | viewer — team-wide |
| GET | `/failures/{failure}` | viewer — full detail incl. latest analysis + evidence + recos |
| POST | `/failures/{failure}/analyze` | member — queue analysis (throttle `analysis`) |
| POST | `/failures/{failure}/reanalyze` | member — force, bypass cache |
| PUT | `/failures/{failure}/resolve` | member — `resolution_type, resolution_note, commit_sha?` |
| PUT | `/failures/{failure}/ignore` | member |
| GET | `/failures/{failure}/similar?limit=5` | viewer |
| GET | `/failures/{failure}/timeline` | viewer |
| GET | `/analyses/{analysis}` | viewer |
| POST | `/analyses/{analysis}/feedback` | member — `was_helpful, root_cause_correct?, correct_category?, comment?` |
| GET | `/signatures` | viewer — recurring error catalogue |
| GET | `/signatures/{signature}` | viewer — every occurrence + known resolution |
| PUT | `/signatures/{signature}/resolution` | admin — mark `is_known` |

```jsonc
// GET /failures/{failure}
{
  "data": {
    "uuid":"…","status":"analyzed","severity":"high",
    "category":"DATABASE","subcategory":"Connection Refused",
    "error_message":"SQLSTATE[HY000] [2002] Connection refused",
    "stage_name":"test","job_name":"backend-tests","exit_code":1,
    "failed_at":"2026-08-30T14:32:10Z","occurrence_index":4,
    "is_flaky":false,"is_transient":false,

    "project":  { "uuid":"…","name":"biker-api","slug":"biker-api" },
    "pipeline": { "uuid":"…","iid":821,"ref":"feature/payment",
                  "commit_short_sha":"a82c91","commit_message":"wire payment webhook",
                  "web_url":"…" },
    "job":      { "uuid":"…","name":"backend-tests","duration_seconds":94,"web_url":"…" },

    // OBSERVED — facts, never AI output. The UI renders this above the analysis, visually separated.
    "observed": {
      "changed_files":[
        {"path":"docker-compose.yml","change_type":"modified","additions":4,"deletions":1,
         "is_config":true,"is_dependency":false},
        {"path":"app/Services/PaymentService.php","change_type":"modified","additions":62,"deletions":8,
         "is_config":false,"is_dependency":false}
      ],
      "previous_pipeline":{"iid":820,"status":"success","finished_at":"…"},
      "log_excerpt_url":"/api/v1/jobs/…/log?mode=excerpt"
    },

    // PIPEMIND ANALYSIS — inference. Always carries confidence + provenance.
    "analysis": {
      "uuid":"…","status":"completed","confidence":0.92,
      "summary":"Database was unavailable when integration tests started.",
      "root_cause":"The database container had not finished its startup sequence before the test job began connecting. docker-compose.yml was modified in this commit and the healthcheck-based dependency was removed.",
      "explanation":"…",
      "is_transient":false,"retry_recommended":false,
      "classification_source":"hybrid","classification_confidence":0.94,
      "used_rag":true,"similar_failures_count":3,
      "model_provider":"gemini","model_name":"gemini-2.0-flash",
      "latency_ms":3820,"cost_usd":0.000412,"cache_hit":false,
      "completed_at":"2026-08-30T14:32:19Z",

      "evidence":[
        {"type":"log_line","content":"SQLSTATE[HY000] [2002] Connection refused",
         "source_ref":"job_logs#L1294","line_number":1294,"weight":0.95},
        {"type":"changed_file","content":"docker-compose.yml — depends_on condition removed",
         "source_ref":"docker-compose.yml","weight":0.88},
        {"type":"historical_failure","content":"Failure #921 — same signature, resolved by adding a healthcheck",
         "source_ref":"failure:uuid","related_failure_uuid":"…","weight":0.81}
      ],

      "feedback": { "given": false, "was_helpful": null }
    },

    "similar_failures":[
      {"uuid":"…","similarity":0.94,"occurred_at":"2026-05-18T…","project_name":"biker-api",
       "root_cause":"Database container not ready","resolution":"Added healthcheck + depends_on condition",
       "resolved":true,"time_to_resolution_seconds":900}
    ],

    "recommendations":[
      {"uuid":"…","title":"Add a database readiness healthcheck",
       "description":"Restore the healthcheck-based depends_on in docker-compose.yml so the test job waits for Postgres.",
       "rationale":"Failure #921 had an identical signature and was resolved this way.",
       "action_type":"edit_file","risk":"low","confidence":0.91,
       "affected_files":["docker-compose.yml"],"has_patch":true,
       "status":"proposed",
       "policy":{"decision":"requires_approval","reason":"edit_file requires approval on this project"}}
    ]
  }
}
```

> **`observed` vs `analysis` is a hard structural split, not a styling choice.** The mockup shows it and the trust model depends on it. Never merge them into one object — the moment a fact and an inference share a shape, the UI cannot honestly distinguish them.

### Recommendations & remediation

| Method | Path | Role |
|---|---|---|
| GET | `/failures/{failure}/recommendations` | viewer |
| POST | `/recommendations/{recommendation}/accept` | member — creates a remediation, policy decides |
| POST | `/recommendations/{recommendation}/reject` | member |
| GET | `/recommendations/{recommendation}/patch` | member — unified diff |
| GET | `/remediations` | viewer — `?status=pending_approval` drives the approvals badge |
| GET | `/remediations/{remediation}` | viewer — full audit trail |
| POST | `/remediations/{remediation}/approve` | admin |
| POST | `/remediations/{remediation}/reject` | admin — `reason` |
| POST | `/remediations/{remediation}/cancel` | admin |
| GET | `/remediation-policies` | admin |
| PUT | `/remediation-policies/{policy}` | owner |
| POST | `/remediation-policies/reset` | owner — restore the 9 defaults |

### Anomalies, knowledge, AI providers

| Method | Path | Role |
|---|---|---|
| GET | `/projects/{project}/anomalies?status=open` | viewer |
| GET | `/anomalies/{anomaly}` | viewer |
| POST | `/anomalies/{anomaly}/acknowledge` | member |
| POST | `/anomalies/{anomaly}/false-positive` | member |
| GET | `/projects/{project}/knowledge` | viewer |
| POST | `/projects/{project}/knowledge` | admin — `type, title, content` or file upload |
| DELETE | `/knowledge/{document}` | admin |
| POST | `/knowledge/{document}/reindex` | admin |
| GET | `/ai-providers` | admin |
| POST | `/ai-providers` | admin |
| PUT | `/ai-providers/{provider}` | admin |
| DELETE | `/ai-providers/{provider}` | admin |
| POST | `/ai-providers/{provider}/test` | admin — round-trip a trivial prompt |
| POST | `/ai-providers/{provider}/default` | admin |
| GET | `/ai/usage?range=30d` | admin — spend, tokens, cache hit rate, per-model breakdown |

### Notifications, search, system

| Method | Path | Role |
|---|---|---|
| GET | `/notifications?unread=1` | viewer |
| GET | `/notifications/count` | viewer — the bell badge |
| POST | `/notifications/{id}/read` | viewer |
| POST | `/notifications/read-all` | viewer |
| GET | `/notification-channels` | admin |
| POST | `/notification-channels` | admin |
| PUT/DELETE | `/notification-channels/{channel}` | admin |
| POST | `/notification-channels/{channel}/test` | admin |
| GET | `/search?q=&types[]=project,pipeline,failure,signature` | viewer — ⌘K |
| GET | `/system/status` | viewer — DB, Redis, queue depth, AI service, provider reachability |
| GET | `/health` | — | no auth, for uptime checks |

### Webhooks — public, no auth, signature-verified

| Method | Path |
|---|---|
| POST | `/webhooks/gitlab/{integration:uuid}` |
| POST | `/webhooks/github/{integration:uuid}` |
| POST | `/webhooks/jenkins/{integration:uuid}` |
| POST | `/webhooks/generic/{integration:uuid}` |

Implemented in file 05.

- [ ] All routes registered in `routes/api.php`, grouped by middleware
- [ ] `php artisan route:list --path=api` matches this table

---

## 4.3 Response conventions

```jsonc
// single resource
{ "data": { … } }

// collection with pagination
{ "data": [ … ],
  "meta": { "current_page":1,"per_page":25,"total":312,"last_page":13 },
  "links": { "first":"…","prev":null,"next":"…","last":"…" } }

// validation error — 422
{ "message":"The given data was invalid.",
  "errors": { "email":["The email field is required."] } }

// domain error — 4xx/5xx
{ "message":"Human-readable sentence the UI can show directly.",
  "error_code":"AI_SERVICE_UNAVAILABLE",
  "retryable": true }
```

**Error codes the frontend switches on** — the mockup's error handling depends on distinguishing these:

```text
UNAUTHENTICATED          TEAM_ACCESS_DENIED        INSUFFICIENT_ROLE
INTEGRATION_UNREACHABLE  INTEGRATION_UNAUTHORIZED  PROVIDER_RATE_LIMITED
AI_SERVICE_UNAVAILABLE   AI_BUDGET_EXCEEDED        AI_PROVIDER_ERROR
ANALYSIS_IN_PROGRESS     ANALYSIS_FAILED           LOG_NOT_AVAILABLE
REMEDIATION_FORBIDDEN    REMEDIATION_EXPIRED       POLICY_LIMIT_REACHED
```

> A failed AI analysis is **not** a failed pipeline, and the UI must never conflate them. That is exactly why these are separate codes rather than a generic 500.

- [ ] `app/Exceptions/PipeMindException.php` with an `errorCode()` and `retryable()` contract
- [ ] Handler renders the shape above for all API requests

---

## 4.4 API Resources

```php
// spec — app/Http/Resources/
UserResource · TeamResource · TeamMemberResource · IntegrationResource
ProjectResource · ProjectCardResource · ProjectOverviewResource
PipelineResource · PipelineListResource · PipelineJobResource · JobLogResource
FailureResource · FailureListResource · FailureDetailResource
AnalysisResource · EvidenceResource · RecommendationResource
RemediationResource · AnomalyResource · ActivityResource
AiProviderResource · AiUsageResource · NotificationResource
```

Two resources per heavy model — a **list** variant and a **detail** variant. `PipelineListResource` returns 9 fields; `PipelineResource` returns everything plus stages, jobs and changes. Loading the detail shape for a 25-row table is how list endpoints get slow.

```php
// ready — always guard against N+1
public function index(Project $project)
{
    $pipelines = QueryBuilder::for($project->pipelines())
        ->allowedFilters(['status', 'ref', 'source', AllowedFilter::scope('between')])
        ->allowedSorts(['created_at', 'duration_seconds', 'iid'])
        ->defaultSort('-created_at')
        ->with(['failures:id,pipeline_id,uuid,category,severity'])
        ->withCount('failedJobs')
        ->paginate($request->integer('per_page', 25));

    return PipelineListResource::collection($pipelines);
}
```

- [ ] All resources written
- [ ] `Model::preventLazyLoading()` enabled in non-production (`AppServiceProvider`)

---

## 4.5 Policies

```bash
# ready
php artisan make:policy TeamPolicy --model=Team
php artisan make:policy ProjectPolicy --model=Project
php artisan make:policy IntegrationPolicy --model=Integration
php artisan make:policy FailurePolicy --model=Failure
php artisan make:policy RemediationPolicy --model=Remediation
php artisan make:policy AiProviderPolicy --model=AiProvider
```

```php
// ready — app/Policies/RemediationPolicy.php  (the one that matters)
public function approve(User $user, Remediation $remediation): bool
{
    // Cannot approve your own request — separation of duties, even on a solo project.
    if ($remediation->requested_by === $user->id) {
        return false;
    }

    return $this->hasRole($user, $remediation->team, ['owner', 'admin'])
        && $remediation->status === 'pending_approval'
        && ! $remediation->isExpired();
}
```

> Self-approval is blocked deliberately. On a one-person team it means the "auto" policy mode is the only path to unattended remediation — which is the correct outcome: unattended actions should be governed by a written policy, not by a person waving through their own request.

- [ ] Six policies implemented and registered
- [ ] Every controller calls `$this->authorize(…)` — verified by a Pest test that walks the route list

---

## 4.6 Controllers

```text
app/Http/Controllers/Api/V1/
├── Auth/           LoginController RegisterController PasswordController
│                   ProfileController TokenController EmailVerificationController
├── TeamController  TeamMemberController TeamInvitationController
├── WorkspaceController          ← summary, projects, activity
├── ProjectController            ← crud + overview + metrics + insights
├── IntegrationController
├── PipelineController  PipelineJobController  JobLogController
├── FailureController   AnalysisController  FailureSignatureController
├── RecommendationController  RemediationController  RemediationPolicyController
├── AnomalyController   KnowledgeController
├── AiProviderController  AiUsageController
├── NotificationController  NotificationChannelController
├── SearchController    SystemStatusController
└── Webhooks/       GitlabWebhookController GithubWebhookController
                    JenkinsWebhookController GenericWebhookController
```

Controllers stay thin. Business logic lives in `app/Services/`:

```text
app/Services/
├── Workspace/   WorkspaceSummaryService  ProjectStatsService
├── Projects/    ProjectOverviewService   ProjectMetricsService  ProjectInsightService
├── Failures/    FailureDetectionService  FailureResolutionService  SignatureService
└── Analysis/    AnalysisOrchestrator     (file 10)
```

- [ ] Controllers + services scaffolded
- [ ] `ProjectOverviewService` returns the full board payload from `project_metrics_daily` in < 100 ms on seeded data

---

## 4.7 Tests

```php
// ready — tests/Feature/Api/WorkspaceTest.php
it('returns the workspace summary shape', function () {
    $user = User::factory()->withTeam()->create();

    $this->actingAs($user)
        ->getJson('/api/v1/workspace/summary')
        ->assertOk()
        ->assertJsonStructure(['data' => [
            'projects'        => ['value','delta','delta_label','trend'],
            'pipelines_today' => ['value','delta','delta_label','trend'],
            'failures_today'  => ['value','delta','positive_direction'],
            'success_rate'    => ['value','unit','delta','trend'],
        ]]);
});

it('never leaks another team\'s projects', function () {
    $mine   = User::factory()->withTeam()->create();
    $theirs = User::factory()->withTeam()->create();
    Project::factory()->for($theirs->currentTeam)->count(3)->create();

    $this->actingAs($mine)
        ->getJson('/api/v1/workspace/projects')
        ->assertOk()
        ->assertJsonCount(0, 'data');
});

it('forbids a viewer from approving a remediation', function () {
    $viewer = User::factory()->withTeam(role: 'viewer')->create();
    $rem    = Remediation::factory()->for($viewer->currentTeam)->pendingApproval()->create();

    $this->actingAs($viewer)
        ->postJson("/api/v1/remediations/{$rem->uuid}/approve")
        ->assertForbidden();
});
```

- [ ] Feature test per controller group
- [ ] A tenancy-leak test for every list endpoint (this is the class of bug that ends projects)

---

## Definition of Done

```bash
php artisan route:list --path=api/v1 | wc -l     # ~95 routes
php artisan test --filter=Api                    # green
curl -s localhost:8000/api/v1/health             # {"status":"ok",...}

# full happy path against seeded data
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"PmAG01@evoxai.ca","password":"password"}' | jq -r '.data.token')

curl -s localhost:8000/api/v1/workspace/summary  -H "Authorization: Bearer $TOKEN" | jq .
curl -s localhost:8000/api/v1/workspace/projects -H "Authorization: Bearer $TOKEN" | jq '.data[0]'
PROJECT=$(curl -s localhost:8000/api/v1/workspace/projects -H "Authorization: Bearer $TOKEN" | jq -r '.data[0].uuid')
curl -s "localhost:8000/api/v1/projects/$PROJECT/overview?range=7d" -H "Authorization: Bearer $TOKEN" | jq 'keys'
```

- [ ] Every payload above renders the mockup numbers from seeded data
- [ ] `/projects/{uuid}/overview` responds in < 150 ms

> The frontend (files 11–16) is built entirely against these seeded responses. Ingestion swaps the data source later without the frontend changing a line — which is the whole point of the contract.

**Next:** [`05-backend-ingestion.md`](05-backend-ingestion.md)
