# 10 — Backend ↔ AI Integration

**Repo:** `PipeMind-back` · **Depends on:** 09 · **Milestone:** M3 ⭐

Laravel calls the Python service, persists the structured result, caches by signature, tracks cost, and exposes it through `GET /failures/{failure}`. When this file is done, **M3 is done** — a real failure becomes a real analysis on screen.

---

## 10.1 The gateway

One class. Nothing else in Laravel may talk HTTP to the AI service.

```php
// ready — app/Services/Ai/AiGateway.php
namespace App\Services\Ai;

use App\Exceptions\Ai\{AiBudgetExceeded, AiServiceUnavailable, AiInvalidResponse};
use Illuminate\Http\Client\{ConnectionException, PendingRequest};
use Illuminate\Support\Facades\Http;

class AiGateway
{
    public function __construct(private readonly AiRequestRecorder $recorder) {}

    protected function client(int $timeout = null): PendingRequest
    {
        return Http::baseUrl(rtrim(config('pipemind.ai.url'), '/'))
            ->withHeaders([
                'X-PipeMind-Token' => config('pipemind.ai.token'),
                'X-Contract'       => config('pipemind.ai.contract_version'),
            ])
            ->timeout($timeout ?? config('pipemind.ai.timeout'))
            ->connectTimeout(5)
            ->acceptJson()
            ->asJson();
    }

    public function processLog(string $rawLog, array $context = []): array
    {
        return $this->call('POST', '/v1/logs/process', [
            'raw_log'          => $rawLog,
            'job_name'         => $context['job_name'] ?? null,
            'stage_name'       => $context['stage_name'] ?? null,
            'exit_code'        => $context['exit_code'] ?? null,
            'strict_redaction' => $context['strict'] ?? true,
        ], timeout: 60);
    }

    public function classify(string $text, ?string $ecosystem = null): array
    {
        return $this->call('POST', '/v1/classify', compact('text', 'ecosystem'), timeout: 20);
    }

    public function embed(string $text): array
    {
        return $this->call('POST', '/v1/embed', compact('text'), timeout: 30);
    }

    public function similar(int $teamId, string $errorMessage, array $opts = []): array
    {
        return $this->call('POST', '/v1/similar', [
            'team_id'       => $teamId,
            'error_message' => $errorMessage,
            'category'      => $opts['category'] ?? null,
            'job_name'      => $opts['job_name'] ?? null,
            'exclude_failure_id' => $opts['exclude'] ?? null,
            'limit'         => $opts['limit'] ?? 5,
        ], timeout: 30);
    }

    public function analyze(array $payload): array
    {
        return $this->call('POST', '/v1/analyze', $payload,
            timeout: config('pipemind.ai.timeout'));
    }

    public function info(): array
    {
        return $this->call('GET', '/v1/info', timeout: 5);
    }

    protected function call(string $method, string $path, array $body = [], ?int $timeout = null): array
    {
        try {
            $res = $this->client($timeout)->send($method, $path, ['json' => $body]);
        } catch (ConnectionException $e) {
            throw new AiServiceUnavailable('The analysis service is unreachable.', previous: $e);
        }

        if ($res->successful()) {
            return $res->json();
        }

        // The AI service returns Laravel's own error shape (file 06), so forward it.
        $code = $res->json('error_code', 'AI_SERVICE_ERROR');
        $msg  = $res->json('message', 'Analysis failed.');

        throw match ($code) {
            'AI_BUDGET_EXCEEDED'   => new AiBudgetExceeded($msg),
            'AI_INVALID_RESPONSE'  => new AiInvalidResponse($msg),
            default                => new AiServiceUnavailable($msg),
        };
    }
}
```

> **No retry logic here.** The Python side already retries the model with backoff (file 09), and the Laravel *job* retries the whole call. Retrying at three layers turns one transient blip into nine model calls and nine times the cost.

- [ ] `AiGateway` implemented, bound as a singleton
- [ ] Typed exceptions created, each carrying an `errorCode()`

---

## 10.2 Context builder

The quality of the analysis is decided here, not in the prompt. Assemble everything the model needs and nothing it doesn't.

```php
// ready — app/Services/Ai/AnalysisContextBuilder.php
namespace App\Services\Ai;

use App\Models\{Failure, Pipeline};

class AnalysisContextBuilder
{
    public function build(Failure $failure): array
    {
        $failure->loadMissing([
            'project', 'pipeline.changes', 'job.log', 'signature',
        ]);

        $project  = $failure->project;
        $pipeline = $failure->pipeline;
        $job      = $failure->job;
        $log      = $job?->log;

        return [
            'contract_version' => config('pipemind.ai.contract_version'),
            'team_id'          => $failure->team_id,

            'failure' => [
                'uuid'             => $failure->uuid,
                'occurrence_index' => $failure->occurrence_index,
                'is_flaky'         => $failure->is_flaky,
                'signature_hash'   => $failure->signature?->hash,
            ],

            'project' => [
                'uuid'           => $project->uuid,
                'name'           => $project->name,
                'tech_stack'     => $project->tech_stack ?? [],
                'provider'       => $project->integration?->provider ?? 'unknown',
                'default_branch' => $project->default_branch,
            ],

            'pipeline' => [
                'iid'              => $pipeline->iid,
                'ref'              => $pipeline->ref,
                'source'           => $pipeline->source,
                'commit_sha'       => $pipeline->commit_short_sha,
                'commit_message'   => \Str::limit($pipeline->commit_message ?? '', 200),
                'duration_seconds' => $pipeline->duration_seconds,

                // The single highest-signal fact available to the model.
                'previous_status'  => $this->previousStatus($pipeline),

                'changed_files'    => $this->changedFiles($pipeline),
            ],

            'job' => [
                'name'             => $job?->name,
                'stage_name'       => $job?->stage_name,
                'status'           => $job?->status,
                'exit_code'        => $failure->exit_code ?? $job?->exit_code,
                'duration_seconds' => $job?->duration_seconds,
                'failure_reason'   => $job?->failure_reason,
                'baseline_duration_seconds' => $this->baseline($failure),
            ],

            // Already redacted by /v1/logs/process during ingestion.
            'log_excerpt' => $log?->excerpt ?? '',
            'error_block' => $log?->error_block,
            'stack_trace' => $log?->stack_trace,

            'use_rag'      => true,
            'use_llm'      => true,
            'llm_override' => $this->providerOverride($failure),
        ];
    }

    /** Status of the last pipeline on this ref before this one. */
    protected function previousStatus(Pipeline $pipeline): ?string
    {
        return $pipeline->project->pipelines()
            ->where('ref', $pipeline->ref)
            ->where('id', '<', $pipeline->id)
            ->whereIn('status', ['success', 'failed'])
            ->latest('id')
            ->value('status');
    }

    /** Config and dependency changes first — they explain far more failures than source edits. */
    protected function changedFiles(Pipeline $pipeline): array
    {
        return $pipeline->changes
            ->sortByDesc(fn ($c) => ($c->is_config ? 2 : 0) + ($c->is_dependency ? 2 : 0))
            ->take(20)
            ->map(fn ($c) => [
                'path'          => $c->file_path,
                'change_type'   => $c->change_type,
                'additions'     => $c->additions,
                'deletions'     => $c->deletions,
                'is_config'     => $c->is_config,
                'is_dependency' => $c->is_dependency,
            ])->values()->all();
    }

    protected function baseline(Failure $failure): ?float
    {
        return \App\Models\JobBaseline::where('project_id', $failure->project_id)
            ->where('job_name', $failure->job_name)
            ->whereIn('ref', [$failure->pipeline->ref, '*'])
            ->orderByRaw("ref = '*'")     // an exact-ref baseline beats the wildcard
            ->value('mean_duration_seconds');
    }

    /** The team's configured provider + key, sent per-request so the AI service stores nothing. */
    protected function providerOverride(Failure $failure): ?array
    {
        $provider = $failure->project->aiProvider
            ?? $failure->project->team->aiProviders()->where('is_default', true)->first();

        if (! $provider) {
            return null;
        }

        // A local_only team never gets a cloud provider, regardless of project config.
        if ($failure->project->team->privacy_mode === 'local_only' && ! $provider->is_local) {
            $provider = $failure->project->team->aiProviders()
                ->where('is_local', true)->where('status', 'active')->first()
                ?? throw new \App\Exceptions\Ai\NoLocalProviderConfigured;
        }

        return [
            'provider'           => $provider->provider,
            'model'              => $provider->model,
            'api_key'            => $provider->api_key,      // decrypted by the cast
            'base_url'           => $provider->base_url,
            'input_cost_per_1k'  => (float) $provider->input_cost_per_1k,
            'output_cost_per_1k' => (float) $provider->output_cost_per_1k,
        ];
    }
}
```

> **`privacy_mode = local_only` is enforced here, in Laravel, not in the AI service.** The boundary that decides whether a team's logs may reach a third party belongs on the side that owns the team record. If no local provider is configured, the analysis fails loudly rather than quietly falling back to the cloud.

- [ ] `AnalysisContextBuilder` implemented
- [ ] Test: a `local_only` team with no local provider throws instead of using Gemini

---

## 10.3 The analysis job

```php
// ready — app/Jobs/AnalyzeFailure.php
namespace App\Jobs;

use App\Exceptions\Ai\{AiBudgetExceeded, AiServiceUnavailable};
use App\Models\{Analysis, Failure};
use App\Services\Ai\{AiGateway, AnalysisCache, AnalysisContextBuilder, AnalysisPersister};
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;
use Illuminate\Queue\Middleware\{RateLimited, WithoutOverlapping};

class AnalyzeFailure implements ShouldQueue
{
    use Queueable;

    public int $tries = 2;
    public int $timeout = 180;
    public array $backoff = [30, 180];

    public function __construct(
        public int $failureId,
        public bool $force = false,
    ) {
        $this->onQueue('analysis');
    }

    public function middleware(): array
    {
        return [
            new WithoutOverlapping("analyze:{$this->failureId}"),
            new RateLimited('ai-analysis'),
        ];
    }

    public function handle(
        AiGateway $ai,
        AnalysisContextBuilder $builder,
        AnalysisCache $cache,
        AnalysisPersister $persister,
    ): void {
        $failure = Failure::withoutGlobalScopes()
            ->with('project.team')
            ->findOrFail($this->failureId);

        withTeam($failure->project->team, function () use ($failure, $ai, $builder, $cache, $persister) {

            if ($failure->status === 'analyzed' && ! $this->force) {
                return;
            }

            // Flaky failures are noise. Analysing the same flake twenty times is
            // the fastest way to exhaust a budget for zero insight.
            if ($failure->is_flaky && ! $this->force) {
                $failure->update(['status' => 'analyzed']);
                return;
            }

            $failure->update(['status' => 'analyzing']);

            $analysis = Analysis::create([
                'failure_id'       => $failure->id,
                'team_id'          => $failure->team_id,
                'status'           => 'running',
                'contract_version' => config('pipemind.ai.contract_version'),
                'started_at'       => now(),
            ]);

            try {
                // Same signature, same project, recent → reuse. This is where most
                // of the cost saving lives once a team has any history at all.
                if (! $this->force && $cached = $cache->get($failure)) {
                    $persister->persistCached($analysis, $failure, $cached);
                    return;
                }

                $result = $ai->analyze($builder->build($failure));

                $persister->persist($analysis, $failure, $result);
                $cache->put($failure, $result);

                EmbedFailure::dispatch($failure->id)->onQueue('analysis');

            } catch (AiBudgetExceeded $e) {
                // Not a retryable failure. Stop, surface it, don't burn attempts.
                $this->markFailed($analysis, $failure, $e->getMessage(), retry: false);
                $this->fail($e);

            } catch (AiServiceUnavailable $e) {
                $this->markFailed($analysis, $failure, $e->getMessage(), retry: true);
                throw $e;                       // let the queue retry

            } catch (\Throwable $e) {
                $this->markFailed($analysis, $failure, $e->getMessage(), retry: false);
                throw $e;
            }
        });
    }

    protected function markFailed(Analysis $analysis, Failure $failure, string $msg, bool $retry): void
    {
        $analysis->update([
            'status'       => 'failed',
            'error'        => \Str::limit($msg, 1000),
            'completed_at' => now(),
        ]);

        if (! $retry) {
            $failure->update(['status' => 'analysis_failed']);
        }
    }

    public function failed(\Throwable $e): void
    {
        Failure::withoutGlobalScopes()
            ->where('id', $this->failureId)
            ->update(['status' => 'analysis_failed']);
    }
}
```

```php
// ready — AppServiceProvider::boot()  — the RateLimited middleware's limiter
RateLimiter::for('ai-analysis', function (object $job) {
    // Per-team, so one noisy workspace cannot starve another.
    $teamId = Failure::withoutGlobalScopes()->where('id', $job->failureId)->value('team_id');

    return Limit::perMinute(10)->by("ai-analysis:{$teamId}");
});
```

- [ ] `AnalyzeFailure` implemented
- [ ] `EmbedFailure` job implemented (calls `/v1/embed`, inserts into `failure_embeddings`)
- [ ] Rate limiter registered

---

## 10.4 Caching

```php
// ready — app/Services/Ai/AnalysisCache.php
namespace App\Services\Ai;

use App\Models\{Analysis, Failure};
use Illuminate\Support\Facades\Cache;

class AnalysisCache
{
    public function get(Failure $failure): ?array
    {
        if (! $hash = $failure->signature?->hash) {
            return null;
        }

        // 1. Hot path: Redis.
        if ($cached = Cache::get($this->key($failure, $hash))) {
            return $cached;
        }

        // 2. Warm path: an existing analysis of the same signature in the same project.
        //    Scoped to the project deliberately — the same error text in a different
        //    codebase can have a genuinely different cause.
        $previous = Analysis::query()
            ->join('failures', 'failures.id', '=', 'analyses.failure_id')
            ->where('failures.project_id', $failure->project_id)
            ->where('failures.signature_id', $failure->signature_id)
            ->where('analyses.status', 'completed')
            ->where('analyses.confidence', '>=', 0.80)
            ->where('analyses.created_at', '>=', now()->subHours(
                config('pipemind.analysis.cache_ttl_hours')
            ))
            ->orderByDesc('analyses.confidence')
            ->select('analyses.*')
            ->first();

        if (! $previous) {
            return null;
        }

        $payload = $this->toPayload($previous);
        Cache::put($this->key($failure, $hash), $payload, now()->addHours(24));

        return $payload;
    }

    public function put(Failure $failure, array $result): void
    {
        if ($hash = $failure->signature?->hash) {
            Cache::put($this->key($failure, $hash), $result, now()->addHours(24));
        }
    }

    protected function key(Failure $failure, string $hash): string
    {
        return "pipemind:analysis:{$failure->project_id}:{$hash}";
    }
}
```

**Cache invalidation rules — write these down, they are easy to get wrong:**

| Event | Action |
|---|---|
| Developer submits feedback marking the analysis wrong | Purge that signature's cache immediately |
| Signature promoted to `is_known` with a resolution | Purge — future analyses should use the confirmed fix |
| Project's AI provider or model changes | Purge the whole project namespace |
| `reanalyze` requested | Bypass, do not purge (keep the old one for comparison) |
| TTL expires (7 days) | Natural expiry |

> **Cache by `(project_id, signature_hash)`, never by signature alone.** A `Connection refused` in a Laravel API and in a React build have identical text and completely different causes. Cross-project cache sharing is how you ship a confidently wrong analysis.

- [ ] `AnalysisCache` implemented
- [ ] Invalidation wired into the feedback endpoint and the provider-update endpoint
- [ ] `cache_hit` recorded on the analysis row

---

## 10.5 Persistence

```php
// ready — app/Services/Ai/AnalysisPersister.php
namespace App\Services\Ai;

use App\Events\{AnalysisCompleted, FailureAnalyzed};
use App\Models\{Analysis, AnalysisEvidence, Failure, Recommendation};
use App\Services\Ai\RemediationPolicyEvaluator;
use Illuminate\Support\Facades\DB;

class AnalysisPersister
{
    public function __construct(
        private readonly AiRequestRecorder $recorder,
        private readonly RemediationPolicyEvaluator $policy,
    ) {}

    public function persist(Analysis $analysis, Failure $failure, array $r): void
    {
        DB::transaction(function () use ($analysis, $failure, $r) {

            $analysis->update([
                'status'                    => 'completed',
                'ai_service_version'        => $r['service_version'] ?? null,
                'category'                  => $r['category'],
                'subcategory'               => $r['subcategory'] ?? null,
                'severity'                  => $r['severity'],
                'confidence'                => $r['confidence'],
                'summary'                   => $r['summary'],
                'root_cause'                => $r['root_cause'],
                'explanation'               => $r['explanation'] ?? null,
                'is_transient'              => $r['is_transient'] ?? false,
                'retry_recommended'         => $r['retry_recommended'] ?? false,
                'classification_source'     => $r['classification_source'],
                'classification_confidence' => $r['classification_confidence'],
                'used_rag'                  => $r['used_rag'] ?? false,
                'similar_failures_count'    => count($r['similar_failures'] ?? []),
                'model_provider'            => $r['usage']['provider'] ?? null,
                'model_name'                => $r['usage']['model'] ?? null,
                'prompt_tokens'             => $r['usage']['prompt_tokens'] ?? 0,
                'completion_tokens'         => $r['usage']['completion_tokens'] ?? 0,
                'cost_usd'                  => $r['usage']['cost_usd'] ?? 0,
                'latency_ms'                => $r['usage']['latency_ms'] ?? null,
                'cache_hit'                 => $r['usage']['cache_hit'] ?? false,
                'raw_response'              => $r,
                'completed_at'              => now(),
            ]);

            $this->storeEvidence($analysis, $r['evidence'] ?? []);
            $this->storeRecommendations($analysis, $failure, $r['recommendations'] ?? []);

            // The analysis is the authority on category/severity — it saw full context,
            // where the ingest-time classifier saw only the error block.
            $failure->update([
                'status'      => 'analyzed',
                'category'    => $r['category'],
                'subcategory' => $r['subcategory'] ?? null,
                'severity'    => $r['severity'],
                'is_transient'=> $r['is_transient'] ?? false,
            ]);

            $failure->signature?->update([
                'category'    => $r['category'],
                'subcategory' => $r['subcategory'] ?? null,
            ]);

            $this->recorder->record($analysis, $failure, $r['usage'] ?? []);
        });

        activity_log($failure->project, 'analysis.completed', 'success',
            $failure->project->name,
            "{$r['category']} · ".round($r['confidence'] * 100)."% confidence",
            subject: $failure,
        );

        AnalysisCompleted::dispatch($analysis->id);
        FailureAnalyzed::dispatch($failure->id);
    }

    protected function storeEvidence(Analysis $analysis, array $items): void
    {
        foreach (array_values($items) as $i => $e) {
            AnalysisEvidence::create([
                'analysis_id' => $analysis->id,
                'type'        => $e['type'] ?? 'log_line',
                'content'     => \Str::limit($e['content'] ?? '', 2000),
                'source_ref'  => $e['source_ref'] ?? null,
                'line_number' => $e['line_number'] ?? null,
                'related_failure_id' => isset($e['related_failure_uuid'])
                    ? Failure::where('uuid', $e['related_failure_uuid'])->value('id')
                    : null,
                'weight'      => min(1, max(0, (float) ($e['weight'] ?? 0.5))),
                'position'    => $i,
            ]);
        }
    }

    protected function storeRecommendations(Analysis $analysis, Failure $failure, array $items): void
    {
        foreach (array_values($items) as $i => $rec) {
            $recommendation = Recommendation::create([
                'analysis_id'    => $analysis->id,
                'failure_id'     => $failure->id,
                'title'          => \Str::limit($rec['title'], 250),
                'description'    => $rec['description'] ?? null,
                'rationale'      => $rec['rationale'] ?? null,
                'action_type'    => $rec['action_type'] ?? 'manual',
                'risk'           => $rec['risk'] ?? 'medium',
                'confidence'     => $rec['confidence'] ?? null,
                'affected_files' => $rec['affected_files'] ?? [],
                'patch'          => $rec['patch'] ?? null,
                'position'       => $i,
            ]);

            // Evaluate the policy now so the UI can show the gate immediately —
            // "Approve" vs "Not allowed" without a second round trip.
            $this->policy->annotate($recommendation);
        }
    }
}
```

```php
// ready — app/Services/Ai/AiRequestRecorder.php
public function record(Analysis $analysis, Failure $failure, array $usage): void
{
    AiRequest::create([
        'team_id'           => $failure->team_id,
        'project_id'        => $failure->project_id,
        'failure_id'        => $failure->id,
        'analysis_id'       => $analysis->id,
        'ai_provider_id'    => $failure->project->ai_provider_id,
        'operation'         => 'analyze',
        'provider'          => $usage['provider'] ?? 'unknown',
        'model'             => $usage['model'] ?? 'unknown',
        'prompt_tokens'     => $usage['prompt_tokens'] ?? 0,
        'completion_tokens' => $usage['completion_tokens'] ?? 0,
        'total_tokens'      => ($usage['prompt_tokens'] ?? 0) + ($usage['completion_tokens'] ?? 0),
        'cost_usd'          => $usage['cost_usd'] ?? 0,
        'latency_ms'        => $usage['latency_ms'] ?? null,
        'cache_hit'         => $usage['cache_hit'] ?? false,
        'status'            => 'success',
    ]);
}
```

> **Record every call, including cache hits and failures.** `ai_requests` is what lets you answer "what did this cost, where did the time go, how often did the cache save us" — and every one of those numbers belongs in your report. A cache hit with `cost_usd = 0` is the row that proves the caching works.

- [ ] `AnalysisPersister` and `AiRequestRecorder` implemented
- [ ] Feedback endpoint purges the cache and writes `analysis_feedback`

---

## 10.6 Wiring it up

`DetectFailure` (file 05) already dispatches `AnalyzeFailure`. Complete the chain:

```php
// ready — app/Jobs/DetectFailure.php, tail end
if ($project->auto_analyze && $this->branchMatches($project, $pipeline->ref)) {
    AnalyzeFailure::dispatch($failure->id)->onQueue('analysis');
}

protected function branchMatches(Project $project, string $ref): bool
{
    $patterns = $project->analyze_on_branches ?: ['*'];

    foreach ($patterns as $pattern) {
        if ($pattern === '*' || \Str::is($pattern, $ref)) {
            return true;
        }
    }

    return false;
}
```

```php
// ready — manual trigger, POST /failures/{failure}/analyze
public function analyze(Failure $failure)
{
    $this->authorize('analyze', $failure);

    if ($failure->status === 'analyzing') {
        return response()->json([
            'message'    => 'Analysis already in progress.',
            'error_code' => 'ANALYSIS_IN_PROGRESS',
            'retryable'  => false,
        ], 409);
    }

    AnalyzeFailure::dispatch($failure->id, force: request()->boolean('force'))
        ->onQueue('analysis');

    return response()->json([
        'message' => 'Analysis queued.',
        'data'    => ['status' => 'queued', 'failure_uuid' => $failure->uuid],
    ], 202);
}
```

**System status** should surface the AI service so a dead Python container is visible, not mysterious:

```php
// ready — GET /system/status
'ai_service' => rescue(fn () => [
    'reachable' => true,
    ...app(AiGateway::class)->info(),
], ['reachable' => false], report: false),
```

- [ ] Auto-analysis fires on failure detection
- [ ] Manual trigger works, returns 409 when already running
- [ ] `/system/status` reports AI service health, model, contract version

---

## 10.7 Tests

```php
// ready — tests/Feature/Ai/AnalyzeFailureTest.php
it('persists a complete analysis', function () {
    Http::fake(['*/v1/analyze' => Http::response([
        'contract_version' => 'v1', 'service_version' => '0.1.0',
        'category' => 'DATABASE', 'subcategory' => 'ConnectionRefused',
        'severity' => 'high', 'confidence' => 0.92,
        'summary' => 'Database was unavailable when integration tests started.',
        'root_cause' => 'The database container had not finished starting.',
        'is_transient' => false, 'retry_recommended' => false,
        'classification_source' => 'hybrid', 'classification_confidence' => 0.94,
        'used_rag' => true,
        'evidence' => [
            ['type' => 'log_line', 'content' => 'SQLSTATE[HY000] [2002] Connection refused',
             'source_ref' => 'job_logs#L1294', 'line_number' => 1294, 'weight' => 0.95],
        ],
        'recommendations' => [
            ['title' => 'Add a database readiness healthcheck', 'description' => '…',
             'action_type' => 'edit_file', 'risk' => 'medium', 'confidence' => 0.91,
             'affected_files' => ['docker-compose.yml']],
        ],
        'similar_failures' => [],
        'usage' => ['provider' => 'gemini', 'model' => 'gemini-2.0-flash',
                    'prompt_tokens' => 2100, 'completion_tokens' => 380,
                    'cost_usd' => 0.000412, 'latency_ms' => 3820, 'cache_hit' => false],
    ])]);

    $failure = Failure::factory()->withJobLog()->create();

    (new AnalyzeFailure($failure->id))->handle(...app()->makeMany([...]));

    $failure->refresh();

    expect($failure->status)->toBe('analyzed')
        ->and($failure->category)->toBe('DATABASE')
        ->and($failure->latestAnalysis->confidence)->toBe(0.92)
        ->and($failure->latestAnalysis->evidence)->toHaveCount(1)
        ->and($failure->recommendations)->toHaveCount(1)
        ->and(AiRequest::where('failure_id', $failure->id)->exists())->toBeTrue();
});

it('reuses a cached analysis for the same signature in the same project', function () { /* … */ });
it('skips flaky failures', function () { /* … */ });
it('does not retry on a budget error', function () { /* … */ });
it('refuses a cloud provider for a local_only team', function () { /* … */ });
```

- [ ] Five tests green

---

## Definition of Done — **M3** ⭐

The full loop, no mocks:

```bash
# 1. everything up
docker compose up -d           # postgres, redis, minio, ai
php artisan horizon &
php artisan serve &

# 2. break something for real in the lab
#    Run pipeline with FAIL_MODE=database

# 3. within ~15 s
php artisan tinker --execute="
  \$f = App\Models\Failure::withoutGlobalScopes()->with('latestAnalysis.evidence','recommendations')->latest('id')->first();
  \$a = \$f->latestAnalysis;
  echo \"status={\$f->status} category={\$f->category} severity={\$f->severity}\n\";
  echo \"confidence={\$a->confidence} source={\$a->classification_source} rag=\".(\$a->used_rag?'y':'n').\"\n\";
  echo \"root_cause: {\$a->root_cause}\n\";
  echo \"evidence=\".\$a->evidence->count().\" recos=\".\$f->recommendations->count().\"\n\";
  echo \"cost=\\\${\$a->cost_usd} latency={\$a->latency_ms}ms\n\";
"

# 4. through the API — the exact payload the frontend will render
curl -s "localhost:8000/api/v1/failures/$FAILURE_UUID" -H "Authorization: Bearer $TOKEN" \
  | jq '{category, severity, observed: .observed.changed_files, analysis: {
      confidence: .analysis.confidence, root_cause: .analysis.root_cause,
      evidence: (.analysis.evidence | length)},
      recommendations: (.recommendations | length)}'

# 5. break it the same way again — second run must hit the cache
#    expect: cache_hit=true, cost_usd=0, latency < 100ms
```

**M3 acceptance:**

- [ ] A real pipeline failure produces a structured analysis in under 15 seconds
- [ ] Every evidence item cites a real log line, file, or historical failure
- [ ] Cost per analysis under $0.01, recorded in `ai_requests`
- [ ] A repeat of the same failure hits the cache at zero cost
- [ ] The AI service being down surfaces as `AI_SERVICE_UNAVAILABLE` — the pipeline still shows as failed, not as broken
- [ ] `/horizon` shows no failed jobs after a full run

---

## Batch 2 complete

Files 06–10 done means the intelligence layer works end to end: redaction, log reduction, signatures, classification, embeddings, similarity, RAG, LLM reasoning, and persistence — with cost tracking and a budget ceiling.

**What you can demo now:** push broken code → PipeMind explains why, cites evidence, points at the commit that caused it, finds the last time it happened, and proposes a fix.

**Batch 3** (files 11–23) makes it visible: the Vue frontend built from `ui/workspace.png` and `ui/project.png`, then real-time updates, remediation approval, anomaly detection, testing, deployment and the stage report.

**Next:** `11-frontend-setup.md`
