# 05 — Backend Ingestion

**Repo:** `PipeMind-back` · **Depends on:** 04 · **Milestone:** M2

Real pipelines flowing in from real CI platforms: provider adapters, signature-verified webhooks, normalization, the queue chain, log retrieval into MinIO, failure detection. After this file, `make fresh` plus a `git push` puts a live pipeline on your board.

---

## 5.1 The adapter contract

Every provider difference lives behind this interface. Nothing outside `app/Integrations/` may know what GitLab is.

```php
// ready — app/Integrations/Contracts/PipelineProvider.php
namespace App\Integrations\Contracts;

use App\Integrations\DTO\{NormalizedPipeline, NormalizedJob, NormalizedCommit, RemoteProject, ProviderIdentity};
use App\Models\{Integration, Project, Pipeline, PipelineJob};

interface PipelineProvider
{
    public static function key(): string;                     // 'gitlab' | 'github' | 'jenkins' | 'generic'

    /** Verify credentials. Throws IntegrationUnauthorized on bad token. */
    public function verify(Integration $i): ProviderIdentity;

    /** Repos/projects the token can see, for the import screen. */
    public function remoteProjects(Integration $i, ?string $search = null, int $page = 1): array;

    /** Register/refresh our webhook on the provider side. Returns the provider's hook id. */
    public function registerWebhook(Integration $i, Project $p, string $url, string $secret): string;
    public function removeWebhook(Integration $i, Project $p, string $hookId): void;

    /** Verify an inbound request actually came from the provider. */
    public function verifySignature(Integration $i, string $rawBody, array $headers): bool;

    /** Which of our internal event types this payload represents, or null to ignore. */
    public function eventType(array $payload, array $headers): ?string;

    /** Provider payload → our model. No DB writes here — pure transformation. */
    public function normalizePipeline(array $payload): NormalizedPipeline;
    public function normalizeJobs(array $payload): array;      // NormalizedJob[]

    /** Authoritative fetches (webhooks are hints; the API is truth). */
    public function fetchPipeline(Integration $i, Project $p, string $externalId): NormalizedPipeline;
    public function fetchJobs(Integration $i, Project $p, string $externalId): array;
    public function fetchJobLog(Integration $i, Project $p, PipelineJob $job): string;
    public function fetchCommitChanges(Integration $i, Project $p, string $sha): array;

    /** Actions — used by remediation in file 18. */
    public function retryJob(Integration $i, Project $p, PipelineJob $job): array;
    public function retryPipeline(Integration $i, Project $p, Pipeline $pipeline): array;
    public function cancelPipeline(Integration $i, Project $p, Pipeline $pipeline): void;
    public function createIssue(Integration $i, Project $p, string $title, string $body): array;
}
```

```php
// ready — app/Integrations/DTO/NormalizedPipeline.php
namespace App\Integrations\DTO;

use Spatie\LaravelData\Data;

class NormalizedPipeline extends Data
{
    public function __construct(
        public string  $externalId,
        public ?int    $iid,
        public string  $provider,
        public string  $status,          // our vocabulary, never the provider's
        public string  $source,
        public string  $ref,
        public bool    $isTag,
        public ?string $commitSha,
        public ?string $commitMessage,
        public ?string $commitAuthorName,
        public ?string $commitAuthorEmail,
        public ?string $commitUrl,
        public ?string $webUrl,
        public ?string $triggeredBy,
        public ?string $queuedAt,
        public ?string $startedAt,
        public ?string $finishedAt,
        public ?int    $durationSeconds,
        public ?int    $queueSeconds,
        public array   $raw = [],
    ) {}
}
```

```php
// ready — app/Integrations/ProviderRegistry.php
class ProviderRegistry
{
    /** @var array<string,class-string<PipelineProvider>> */
    protected array $providers = [
        'gitlab'  => GitlabProvider::class,
        'github'  => GithubProvider::class,
        'jenkins' => JenkinsProvider::class,
        'generic' => GenericProvider::class,
    ];

    public function for(Integration $integration): PipelineProvider
    {
        $class = $this->providers[$integration->provider]
            ?? throw new UnsupportedProvider($integration->provider);

        return app($class);
    }
}
```

- [ ] Contract, DTOs and registry created
- [ ] `ProviderRegistry` bound as a singleton

---

## 5.2 Status normalization

The single most valuable table in this file. Get it wrong and every chart lies.

| Ours | GitLab | GitHub Actions (`status`/`conclusion`) | Jenkins (`result`) |
|---|---|---|---|
| `queued` | `created`, `waiting_for_resource`, `preparing`, `pending` | `queued`, `requested`, `waiting`, `pending` | `null` + `inQueue` |
| `running` | `running` | `in_progress` | `null` + building |
| `success` | `success` | `completed`/`success` | `SUCCESS` |
| `failed` | `failed` | `completed`/`failure` | `FAILURE`, `UNSTABLE` |
| `canceled` | `canceled` | `completed`/`cancelled` | `ABORTED` |
| `skipped` | `skipped` | `completed`/`skipped`, `neutral` | `NOT_BUILT` |
| `manual` | `manual`, `scheduled` | `action_required` | — |
| `timeout` | `failed` + `failure_reason=job_execution_timeout` | `completed`/`timed_out` | — |

```php
// ready — app/Integrations/Support/StatusMapper.php
final class StatusMapper
{
    private const GITLAB = [
        'created' => 'queued', 'waiting_for_resource' => 'queued', 'preparing' => 'queued',
        'pending' => 'queued', 'running' => 'running', 'success' => 'success',
        'failed' => 'failed', 'canceled' => 'canceled', 'canceling' => 'running',
        'skipped' => 'skipped', 'manual' => 'manual', 'scheduled' => 'manual',
    ];

    public static function gitlab(string $status, ?string $failureReason = null): string
    {
        $mapped = self::GITLAB[$status] ?? 'queued';

        // GitLab reports a timeout as a plain failure — the reason is the only signal,
        // and timeouts must be distinguishable because they are usually transient.
        if ($mapped === 'failed' && $failureReason === 'job_execution_timeout') {
            return 'timeout';
        }

        return $mapped;
    }

    public static function github(string $status, ?string $conclusion): string
    {
        if ($status !== 'completed') {
            return match ($status) {
                'in_progress' => 'running',
                'queued', 'requested', 'waiting', 'pending' => 'queued',
                default => 'queued',
            };
        }

        return match ($conclusion) {
            'success' => 'success',
            'failure' => 'failed',
            'cancelled' => 'canceled',
            'timed_out' => 'timeout',
            'skipped', 'neutral' => 'skipped',
            'action_required' => 'manual',
            default => 'failed',
        };
    }

    public static function jenkins(?string $result, bool $building = false): string
    {
        if ($building || $result === null) {
            return $building ? 'running' : 'queued';
        }

        return match (strtoupper($result)) {
            'SUCCESS' => 'success',
            'FAILURE', 'UNSTABLE' => 'failed',
            'ABORTED' => 'canceled',
            'NOT_BUILT' => 'skipped',
            default => 'failed',
        };
    }
}
```

> `UNSTABLE` in Jenkins means "built, but tests failed" — map it to `failed`, not `success`. Teams that treat unstable as green are the ones with a broken test suite nobody notices.

- [ ] `StatusMapper` implemented with a unit test per row of the table above

---

## 5.3 GitLab provider (do this one first)

```php
// ready — app/Integrations/Providers/GitlabProvider.php  (key methods)
class GitlabProvider implements PipelineProvider
{
    public static function key(): string { return 'gitlab'; }

    protected function http(Integration $i): PendingRequest
    {
        return Http::baseUrl(rtrim($i->base_url, '/').'/api/v4')
            ->withHeaders(['PRIVATE-TOKEN' => $i->credentials['token']])
            ->timeout(30)
            ->retry(3, 500, throw: false)
            ->acceptJson();
    }

    public function verifySignature(Integration $i, string $rawBody, array $headers): bool
    {
        $token = $headers['x-gitlab-token'][0] ?? '';

        // hash_equals, never ==, and never a substring check.
        return hash_equals($i->webhook_secret, $token);
    }

    public function eventType(array $payload, array $headers): ?string
    {
        return match ($payload['object_kind'] ?? null) {
            'pipeline' => 'pipeline',
            'build'    => 'job',
            default    => null,          // ignore push/issue/note events entirely
        };
    }

    public function normalizePipeline(array $payload): NormalizedPipeline
    {
        $a = $payload['object_attributes'];
        $c = $payload['commit'] ?? [];

        return new NormalizedPipeline(
            externalId:        (string) $a['id'],
            iid:               $a['iid'] ?? null,
            provider:          'gitlab',
            status:            StatusMapper::gitlab($a['status']),
            source:            $a['source'] ?? 'push',
            ref:               $a['ref'],
            isTag:             (bool) ($a['tag'] ?? false),
            commitSha:         $a['sha'] ?? null,
            commitMessage:     $c['message'] ?? null,
            commitAuthorName:  $c['author']['name'] ?? null,
            commitAuthorEmail: $c['author']['email'] ?? null,
            commitUrl:         $c['url'] ?? null,
            webUrl:            $a['url'] ?? null,
            triggeredBy:       $payload['user']['name'] ?? null,
            queuedAt:          $a['created_at'] ?? null,
            startedAt:         $a['started_at'] ?? null,
            finishedAt:        $a['finished_at'] ?? null,
            durationSeconds:   $a['duration'] ?? null,
            queueSeconds:      $a['queued_duration'] ?? null,
            raw:               $payload,
        );
    }

    public function fetchJobLog(Integration $i, Project $p, PipelineJob $job): string
    {
        // Plain text, single request. This is why GitLab is the right first integration.
        $res = $this->http($i)
            ->withOptions(['stream' => true])
            ->get("/projects/{$p->external_id}/jobs/{$job->external_id}/trace");

        throw_if($res->status() === 404, LogNotAvailable::class, 'Log expired or job never ran');
        $res->throw();

        return $res->body();
    }

    public function fetchCommitChanges(Integration $i, Project $p, string $sha): array
    {
        $res = $this->http($i)->get("/projects/{$p->external_id}/repository/commits/{$sha}/diff");

        return collect($res->json())->map(fn ($d) => [
            'file_path'   => $d['new_path'],
            'old_path'    => $d['old_path'] !== $d['new_path'] ? $d['old_path'] : null,
            'change_type' => match (true) {
                $d['new_file']     => 'added',
                $d['deleted_file'] => 'deleted',
                $d['renamed_file'] => 'renamed',
                default            => 'modified',
            },
            'additions'   => substr_count($d['diff'] ?? '', "\n+"),
            'deletions'   => substr_count($d['diff'] ?? '', "\n-"),
        ])->all();
    }

    public function retryJob(Integration $i, Project $p, PipelineJob $job): array
    {
        return $this->http($i)
            ->post("/projects/{$p->external_id}/jobs/{$job->external_id}/retry")
            ->throw()->json();
    }
}
```

**Webhook setup on the GitLab side** — `registerWebhook` POSTs to `/projects/{id}/hooks`:

```json
{
  "url": "https://pipemind.example/webhooks/gitlab/{integration_uuid}",
  "token": "{webhook_secret}",
  "pipeline_events": true,
  "job_events": true,
  "push_events": false,
  "enable_ssl_verification": true
}
```

- [ ] `GitlabProvider` fully implemented
- [ ] Token needs scope `api` (read-only `read_api` cannot retry jobs — document this in the UI)
- [ ] `verify()` returns the GitLab user + scopes so the integrations screen can show them

---

## 5.4 GitHub Actions provider

Two real differences from GitLab, both handled here:

**1. Logs come as a ZIP of per-step files.**

```php
// ready — app/Integrations/Providers/GithubProvider.php
public function fetchJobLog(Integration $i, Project $p, PipelineJob $job): string
{
    // Returns 302 → a short-lived signed blob URL. Do not follow with auth headers attached.
    $res = $this->http($i)
        ->withoutRedirecting()
        ->get("/repos/{$p->external_path}/actions/jobs/{$job->external_id}/logs");

    throw_if($res->status() === 404, LogNotAvailable::class, 'Log expired (GitHub retains 90 days)');

    $url = $res->header('Location') ?: throw new LogNotAvailable('No log location returned');

    // Plain GET, no Authorization header — the URL is already signed and
    // re-sending credentials to blob storage gets the request rejected.
    $body = Http::timeout(120)->get($url)->throw()->body();

    return str_starts_with($body, "PK\x03\x04")
        ? $this->flattenLogZip($body)
        : $body;
}

/** Job-level endpoints usually return plain text; run-level returns a zip of step files. */
protected function flattenLogZip(string $zipBytes): string
{
    $tmp = tempnam(sys_get_temp_dir(), 'ghlog');
    file_put_contents($tmp, $zipBytes);

    $zip = new \ZipArchive;
    throw_unless($zip->open($tmp) === true, LogNotAvailable::class, 'Corrupt log archive');

    $names = [];
    for ($n = 0; $n < $zip->numFiles; $n++) {
        $names[] = $zip->getNameIndex($n);
    }

    // Step files are name-prefixed with their ordinal ("3_Run tests.txt") — sort to restore order.
    natsort($names);

    $out = '';
    foreach ($names as $name) {
        if (str_ends_with($name, '/')) continue;
        $out .= "\n===== {$name} =====\n".$zip->getFromName($name);
    }

    $zip->close();
    @unlink($tmp);

    return $out;
}
```

**2. Signature is HMAC-SHA256 over the raw body.**

```php
// ready
public function verifySignature(Integration $i, string $rawBody, array $headers): bool
{
    $sent = $headers['x-hub-signature-256'][0] ?? '';
    $expected = 'sha256='.hash_hmac('sha256', $rawBody, $i->webhook_secret);

    return hash_equals($expected, $sent);
}
```

> The raw body must be the **exact bytes received**. If any middleware has already decoded and re-encoded the JSON, the HMAC will never match. Capture `$request->getContent()` before anything touches it.

Events to subscribe: `workflow_run`, `workflow_job`. Map `workflow_run` → pipeline, `workflow_job` → job.

- [ ] `GithubProvider` implemented
- [ ] PAT scopes documented: `repo` + `actions:read` (classic) or fine-grained `Actions: read/write`

---

## 5.5 Jenkins & generic providers

Jenkins has no first-class webhook payload for pipelines, so we meet it where it is: a snippet the user pastes into their `Jenkinsfile`.

```groovy
// ready — give this to users on the integrations screen
pipeline {
  agent any
  environment {
    PIPEMIND_URL  = 'https://pipemind.example/webhooks/jenkins/INTEGRATION_UUID'
    PIPEMIND_HOOK = credentials('pipemind-webhook-secret')
  }
  post {
    always {
      script {
        def body = groovy.json.JsonOutput.toJson([
          event      : 'build',
          job        : env.JOB_NAME,
          build      : env.BUILD_NUMBER,
          result     : currentBuild.currentResult,
          building   : false,
          duration   : currentBuild.duration,
          started_at : currentBuild.startTimeInMillis,
          branch     : env.GIT_BRANCH,
          commit     : env.GIT_COMMIT,
          url        : env.BUILD_URL,
          timestamp  : System.currentTimeMillis()
        ])
        def sig = body.bytes.encodeHex().toString()   // replace with HMAC in production
        sh """curl -sS -X POST '${PIPEMIND_URL}' \
              -H 'Content-Type: application/json' \
              -H 'X-PipeMind-Token: ${PIPEMIND_HOOK}' \
              -H 'X-PipeMind-Timestamp: ${System.currentTimeMillis()}' \
              --data '${body}'"""
      }
    }
  }
}
```

Jenkins logs come from `{BUILD_URL}consoleText` — plain text, Basic auth with user + API token.

**Generic provider** accepts the documented envelope so any platform can integrate:

```jsonc
// POST /webhooks/generic/{integration_uuid}
// Headers: X-PipeMind-Token, X-PipeMind-Timestamp
{
  "event": "pipeline",                       // pipeline | job
  "provider": "custom",
  "external_id": "run-9931",
  "iid": 9931,
  "status": "failed",                        // our vocabulary directly
  "ref": "feature/payment",
  "commit": { "sha": "a82c91…", "message": "…", "author_name": "…", "author_email": "…" },
  "started_at": "2026-08-30T14:30:00Z",
  "finished_at": "2026-08-30T14:32:14Z",
  "duration_seconds": 134,
  "web_url": "https://ci.example/run/9931",
  "jobs": [
    { "external_id":"j1","name":"backend-tests","stage":"test","status":"failed",
      "exit_code":1,"started_at":"…","finished_at":"…","duration_seconds":94,
      "log": "…inline log text, optional, max 5 MB…" }
  ]
}
```

- [ ] `JenkinsProvider` + `GenericProvider` implemented
- [ ] Generic envelope documented in `PipeMind-data/contracts/v1/generic-webhook.md`
- [ ] Both verify `X-PipeMind-Token` with `hash_equals` and reject timestamps older than the configured tolerance

---

## 5.6 Webhook ingress

The controller does four things and nothing else. Everything real happens on a queue.

```php
// ready — app/Http/Controllers/Api/V1/Webhooks/WebhookController.php
public function __invoke(Request $request, string $provider, string $integrationUuid)
{
    $integration = Integration::withoutGlobalScopes()
        ->where('uuid', $integrationUuid)
        ->where('provider', $provider)
        ->first();

    // Same response for "unknown integration" and "bad signature" — never confirm
    // to an unauthenticated caller that a given integration UUID exists.
    if (! $integration) {
        return response()->json(['message' => 'Invalid webhook'], 401);
    }

    $raw = $request->getContent();
    $adapter = app(ProviderRegistry::class)->for($integration);

    if (! $adapter->verifySignature($integration, $raw, $request->headers->all())) {
        Log::warning('pipemind.webhook.bad_signature', [
            'integration' => $integration->id,
            'ip' => $request->ip(),
        ]);

        return response()->json(['message' => 'Invalid webhook'], 401);
    }

    $payload   = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    $eventType = $adapter->eventType($payload, $request->headers->all());

    if (! $eventType) {
        return response()->json(['status' => 'ignored'], 202);
    }

    // Idempotency: the unique index does the work. A duplicate delivery is a no-op.
    try {
        $event = PipelineEvent::create([
            'integration_id'       => $integration->id,
            'provider'             => $provider,
            'event_type'           => $eventType,
            'external_delivery_id' => $this->deliveryId($request, $payload),
            'signature_valid'      => true,
            'payload'              => $payload,
            'headers'              => $this->safeHeaders($request),
        ]);
    } catch (UniqueConstraintViolationException) {
        return response()->json(['status' => 'duplicate'], 202);
    }

    ProcessPipelineEvent::dispatch($event->id)->onQueue('ingestion');

    $integration->forceFill(['last_event_at' => now()])->saveQuietly();

    return response()->json(['status' => 'accepted', 'event' => $event->uuid], 202);
}
```

**Rules, all of them non-optional:**

1. **Respond in under 200 ms.** GitLab disables a webhook after repeated timeouts. Persist and dispatch; never process inline.
2. **Always 202 on accept**, never 200 — it accurately says "queued, not done".
3. **Never leak existence.** Unknown integration and bad signature return the identical response.
4. **Strip auth headers before storing.** `safeHeaders()` drops `X-Gitlab-Token`, `X-Hub-Signature-256`, `Authorization`, `Cookie`.
5. **Exclude webhook routes from CSRF** and from the `api` throttle; apply the `webhooks` limiter instead.

- [ ] Four webhook routes registered in `routes/api.php` outside the auth group
- [ ] Signature failure logged with IP, never with the payload
- [ ] Replay test: post the same delivery twice → second returns `duplicate`, one event row exists

---

## 5.7 The job chain

```text
webhook (202)
   │
   ▼
ProcessPipelineEvent            queue: ingestion
   ├── resolve project (external_id → project); unknown → mark skipped, stop
   ├── upsert pipeline (normalize; API refetch if the payload is partial)
   ├── upsert stages + jobs
   ├── write activity_log
   ├── broadcast PipelineUpdated                        → file 17
   └── if terminal status:
         ├── SyncCommitChanges     ──► queue: ingestion
         ├── for each failed job: FetchJobLog ──► queue: logs
         └── RefreshProjectStats   ──► queue: metrics
   │
   ▼
FetchJobLog                     queue: logs
   ├── provider->fetchJobLog()
   ├── enforce max_log_bytes (tail-truncate, set truncated=true)
   ├── stream to MinIO: logs/{project_uuid}/{pipeline_iid}/{job_id}.log
   ├── sha256 checksum
   └── create job_logs row  ──► ProcessJobLog
   │
   ▼
ProcessJobLog                   queue: logs
   ├── POST ai:/v1/logs/process   (redact + extract + signature)   → file 07
   ├── store excerpt, error_block, stack_trace, redaction metadata
   ├── upsert failure_signature (team-scoped, by hash)
   └── DetectFailure
   │
   ▼
DetectFailure                   queue: ingestion
   ├── create failures row (category from the signature, severity from rules)
   ├── occurrence_index = count of this signature in this project
   ├── flaky check: same signature + same commit_sha, previously passed → is_flaky
   ├── activity_log: failure.detected
   ├── broadcast FailureDetected
   └── if project.auto_analyze && ref matches: AnalyzeFailure ──► queue: analysis  (file 10)
```

```php
// ready — app/Jobs/ProcessPipelineEvent.php  (shape every job must follow)
class ProcessPipelineEvent implements ShouldQueue
{
    use Queueable;

    public int $tries = 3;
    public int $timeout = 120;
    public array $backoff = [10, 60, 300];

    public function __construct(public int $eventId)
    {
        $this->onQueue('ingestion');
    }

    /** Two events for the same pipeline must not interleave. */
    public function middleware(): array
    {
        $event = PipelineEvent::withoutGlobalScopes()->find($this->eventId);

        return [
            (new WithoutOverlapping("pipeline-event:{$event?->integration_id}:{$event?->external_object_id}"))
                ->releaseAfter(5)
                ->expireAfter(120),
        ];
    }

    public function handle(ProviderRegistry $registry, PipelineIngestor $ingestor): void
    {
        $event = PipelineEvent::withoutGlobalScopes()->findOrFail($this->eventId);

        if ($event->processing_status === 'processed') {
            return;                                   // re-delivery after a partial failure
        }

        $integration = $event->integration()->withoutGlobalScopes()->firstOrFail();

        // MANDATORY on every queued job: bind the team or the global scope sees nothing.
        withTeam($integration->team, function () use ($event, $registry, $ingestor, $integration) {
            $event->update(['processing_status' => 'processing', 'attempts' => $event->attempts + 1]);

            $adapter = $registry->for($integration);
            $ingestor->ingest($integration, $adapter, $event);

            $event->update(['processing_status' => 'processed', 'processed_at' => now()]);
        });
    }

    public function failed(\Throwable $e): void
    {
        PipelineEvent::withoutGlobalScopes()->where('id', $this->eventId)->update([
            'processing_status' => 'failed',
            'processing_error'  => Str::limit($e->getMessage(), 2000),
        ]);
    }
}
```

> **`WithoutOverlapping` is not optional here.** GitLab fires `pipeline` and several `build` events within the same second. Concurrent workers upserting the same pipeline row produce lost updates and duplicate jobs. Lock on the pipeline's external id.

**Jobs to implement:**

| Job | Queue | Notes |
|---|---|---|
| `ProcessPipelineEvent` | ingestion | above |
| `SyncPipeline` | ingestion | authoritative API refetch; used by reconciliation |
| `SyncCommitChanges` | ingestion | diff → `commit_changes`, sets `is_config`/`is_dependency` |
| `FetchJobLog` | logs | streams to MinIO, never `file_get_contents` into memory |
| `ProcessJobLog` | logs | calls the AI service's log endpoint |
| `DetectFailure` | ingestion | creates the `failures` row |
| `RefreshProjectStats` | metrics | denormalised counters on `projects` |
| `ReconcilePipelines` | ingestion | scheduled; rescues pipelines stuck in `running` |

- [ ] All eight jobs implemented
- [ ] Every one wraps its work in `withTeam()`
- [ ] Every one is idempotent — re-running must not duplicate rows

---

## 5.8 Log storage

```php
// ready — app/Services/Logs/LogStorage.php
public function store(PipelineJob $job, string $contents): JobLog
{
    $project = $job->pipeline->project;
    $max     = config('pipemind.ingestion.max_log_bytes');
    $size    = strlen($contents);
    $truncated = false;

    if ($size > $max) {
        // Keep the TAIL. The error is at the end of a CI log, essentially always.
        $contents  = "…[truncated: {$size} bytes, keeping last {$max}]…\n"
                   . substr($contents, -$max);
        $truncated = true;
    }

    $path = sprintf('logs/%s/%d/%d.log', $project->uuid, $job->pipeline->iid ?? 0, $job->id);

    Storage::disk('logs')->put($path, $contents, ['ContentType' => 'text/plain']);

    return JobLog::updateOrCreate(
        ['job_id' => $job->id],
        [
            'pipeline_id'     => $job->pipeline_id,
            'project_id'      => $project->id,
            'storage_disk'    => 'logs',
            'storage_path'    => $path,
            'size_bytes'      => $size,
            'line_count'      => substr_count($contents, "\n"),
            'checksum_sha256' => hash('sha256', $contents),
            'truncated'       => $truncated,
            'fetched_at'      => now(),
        ]
    );
}
```

Rules:
- Only fetch logs for **failed** and **canceled** jobs (`config('pipemind.ingestion.fetch_logs_for_statuses')`). Green-job logs are pure storage cost.
- Never load a whole log into a string when serving it — the download endpoint returns a **temporary signed S3 URL** (`Storage::temporaryUrl($path, now()->addMinutes(15))`).
- The stored object is the **unredacted original**. Redaction happens on the copy sent to the AI. Losing the original destroys reproducibility, and you need it for the report.
- Lifecycle-expire objects after `retention.raw_logs_days`; the `job_logs` row and its excerpt survive.

- [ ] `LogStorage` implemented
- [ ] `GET /jobs/{job}/log/download` returns a signed URL, not bytes
- [ ] MinIO lifecycle rule configured

---

## 5.9 Failure detection

```php
// spec — app/Services/Failures/FailureDetectionService.php

// Severity is a deterministic rule, not an AI decision. It must be stable
// and explainable before any model has run.
// critical: deploy stage failed on the default branch, OR a production environment
// high    : any failure on the default branch, OR the 3rd+ occurrence in 24h
// medium  : failure on a feature branch
// low     : allow_failure job, or a signature already known to be transient

// Flaky detection:
//   same signature + same commit_sha, where an earlier attempt succeeded
//   → is_flaky = true, severity downgraded one level, no auto-analysis
//   (analysing the same flake ten times is the fastest way to burn your budget)

// Transient detection (pre-LLM, from the signature):
//   network timeouts, 5xx from a registry, "connection reset by peer",
//   runner disappearance, rate limits → is_transient = true, retry_recommended
```

- [ ] `FailureDetectionService` implemented with unit tests per severity rule
- [ ] Flaky and transient rules covered by tests

---

## 5.10 Reconciliation

Webhooks get lost. Plan for it.

```php
// spec — app/Console/Commands/ReconcilePipelines.php
// Every 15 minutes:
//   1. pipelines where status IN ('queued','running')
//      AND updated_at < now() - max(10 min, project p95 duration × 2)
//   2. SyncPipeline for each → authoritative provider fetch
//   3. still running after 6h → mark 'timeout', log an activity entry
//   4. integrations with no last_event_at in 24h AND active projects
//      → status 'error', last_error 'No events received in 24h'
//      → surfaces on the integrations screen so a dead webhook is visible
```

- [ ] Command implemented and scheduled
- [ ] Manual test: stop the queue worker, run a pipeline, restart, confirm reconciliation catches it

---

## 5.11 Integration tests

```php
// ready — tests/Feature/Ingestion/GitlabWebhookTest.php
it('ingests a failed pipeline end to end', function () {
    Queue::fake([]);                     // run jobs synchronously
    Http::fake([
        '*/jobs/*/trace' => Http::response(
            file_get_contents(base_path('tests/fixtures/gitlab/failed-db-test.log'))
        ),
        '*/repository/commits/*/diff' => Http::response([
            ['new_path' => 'docker-compose.yml', 'old_path' => 'docker-compose.yml',
             'new_file' => false, 'deleted_file' => false, 'renamed_file' => false,
             'diff' => "@@\n-    depends_on:\n+    depends_on: [db]\n"],
        ]),
    ]);

    $integration = Integration::factory()->gitlab()->create();
    $project     = Project::factory()->for($integration)->create(['external_id' => '42']);
    $payload     = json_decode(file_get_contents(
        base_path('tests/fixtures/gitlab/pipeline-failed.json')
    ), true);

    $this->postJson("/webhooks/gitlab/{$integration->uuid}", $payload, [
        'X-Gitlab-Token' => $integration->webhook_secret,
        'X-Gitlab-Event' => 'Pipeline Hook',
    ])->assertStatus(202);

    expect($project->pipelines()->count())->toBe(1);

    $pipeline = $project->pipelines()->first();
    expect($pipeline->status)->toBe('failed')
        ->and($pipeline->jobs()->where('status', 'failed')->count())->toBe(1)
        ->and($pipeline->changes()->where('is_config', true)->count())->toBe(1)
        ->and($project->failures()->count())->toBe(1);
});

it('rejects a webhook with a bad signature', function () {
    $integration = Integration::factory()->gitlab()->create();

    $this->postJson("/webhooks/gitlab/{$integration->uuid}", ['object_kind' => 'pipeline'],
        ['X-Gitlab-Token' => 'wrong'])->assertStatus(401);

    expect(PipelineEvent::count())->toBe(0);
});

it('treats a redelivered webhook as a duplicate', function () { /* … */ });
```

**Fixtures to capture** (`tests/fixtures/{gitlab,github,jenkins}/`) — record these from your real lab instance in file 01, do not hand-write them:

```text
pipeline-success.json   pipeline-failed.json   pipeline-running.json
job-failed.json         job-success.json
failed-db-test.log      failed-npm-dependency.log   failed-docker-space.log
failed-phpunit.log      failed-timeout.log
```

- [ ] Fixtures captured from the real lab GitLab
- [ ] Ingestion tests green for all three providers

---

## Definition of Done

Live, end to end, no mocks:

```bash
# 1. lab GitLab running, integration created + webhook registered via the API
# 2. workers up
php artisan horizon

# 3. trigger a real failure in the lab project
#    Run pipeline with FAIL_MODE=database

# 4. within ~10 seconds:
php artisan tinker --execute="
  \$p = App\Models\Pipeline::withoutGlobalScopes()->latest('id')->first();
  echo \$p->iid.' '.\$p->status.' jobs='.\$p->jobs()->count()
      .' failed='.\$p->jobs()->where('status','failed')->count()
      .' changes='.\$p->changes()->count()
      .' failures='.\$p->failures()->count().PHP_EOL;
"
# expected:  <iid> failed jobs=3 failed=1 changes=N failures=1

# 5. the log is in object storage
docker exec pipemind-minio mc ls -r local/pipemind-logs/

# 6. the API serves it
curl -s "localhost:8000/api/v1/projects/$PROJECT/pipelines" -H "Authorization: Bearer $TOKEN" | jq '.data[0]'
```

- [ ] A real push produces a pipeline row, jobs, commit changes, a stored log and a failure
- [ ] `/horizon` shows no failed jobs
- [ ] Replaying the same webhook creates nothing new
- [ ] Killing the worker mid-run and restarting still converges to the correct state

---

## Batch 1 complete

Files 01–05 done means: infrastructure up, schema migrated, API serving, real pipelines ingesting.

**Batch 2** (files 06–10) builds the intelligence layer — the Python service, redaction, log processing, classification, LLM + RAG, and the Laravel↔Python integration that produces the analysis shown in `GET /failures/{failure}`.

**Batch 3** (files 11–23) builds the frontend from `ui/workspace.png` and `ui/project.png`, then real-time, remediation, anomalies, testing, deployment and the report.

**Next:** `06-ai-service-setup.md`
