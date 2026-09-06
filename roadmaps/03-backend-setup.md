# 03 — Backend Setup

**Repo:** `PipeMind-back` · **Depends on:** 02 · **Milestone:** M1

Laravel 12 installed, all 31 tables migrated, models with relationships, factories, a seeder that produces a realistic demo workspace, Horizon running.

---

## 3.1 Install

```bash
# ready
cd PipeMind-back
composer create-project laravel/laravel . "^12.0"

composer require \
  laravel/sanctum \
  laravel/horizon \
  predis/predis \
  league/flysystem-aws-s3-v3 \
  spatie/laravel-data \
  spatie/laravel-query-builder \
  pgvector/pgvector

composer require --dev \
  pestphp/pest --with-all-dependencies \
  pestphp/pest-plugin-laravel \
  larastan/larastan \
  laravel/pint

php artisan install:api          # publishes Sanctum config + api.php
php artisan horizon:install
php artisan vendor:publish --tag=sanctum-migrations
```

- [ ] Laravel 12 installed, `php artisan --version` prints 12.x
- [ ] `.env` copied from the `.env.example` in file 01
- [ ] `php artisan key:generate`

> **Generate the key before you seed.** `integrations.credentials` and
> `ai_providers.api_key` use the `encrypted` cast, so seeding without an `APP_KEY`
> dies with `MissingAppKeyException` partway through — leaving a half-populated
> database that looks like a seeder bug. Back the key up too: losing it makes every
> encrypted credential in the database permanently unreadable.

### Composer scripts

```json
// ready — add to composer.json "scripts"
"lint":     "pint",
"analyse":  "phpstan analyse --memory-limit=1G",
"test":     "pest",
"schema:check": "php artisan pipemind:schema-check"
```

---

## 3.2 Config

```php
// ready — config/database.php → connections.pgsql (confirm these)
'pgsql' => [
    'driver'   => 'pgsql',
    'host'     => env('DB_HOST', '127.0.0.1'),
    'port'     => env('DB_PORT', '5432'),
    'database' => env('DB_DATABASE'),
    'username' => env('DB_USERNAME'),
    'password' => env('DB_PASSWORD'),
    'charset'  => 'utf8',
    'search_path' => 'public',
    'sslmode'  => 'prefer',
],
```

```php
// ready — config/filesystems.php → disks
'logs' => [
    'driver'   => 's3',
    'key'      => env('AWS_ACCESS_KEY_ID'),
    'secret'   => env('AWS_SECRET_ACCESS_KEY'),
    'region'   => env('AWS_DEFAULT_REGION'),
    'bucket'   => env('AWS_BUCKET', 'pipemind-logs'),
    'endpoint' => env('AWS_ENDPOINT'),
    'use_path_style_endpoint' => env('AWS_USE_PATH_STYLE_ENDPOINT', true),
    'throw'    => true,
],
```

```php
// ready — config/pipemind.php  (new file)
<?php
return [
    'ai' => [
        'url'              => env('AI_SERVICE_URL', 'http://localhost:8001'),
        'token'            => env('AI_SERVICE_TOKEN'),
        'timeout'          => (int) env('AI_SERVICE_TIMEOUT', 120),
        'contract_version' => env('AI_CONTRACT_VERSION', 'v1'),
        'retries'          => 2,
    ],

    'ingestion' => [
        // reject webhooks whose timestamp is older than this (replay protection)
        'webhook_tolerance_seconds' => (int) env('PIPEMIND_WEBHOOK_TOLERANCE_SECONDS', 300),
        'max_log_bytes'             => 50 * 1024 * 1024,   // 50 MB hard cap per job log
        'fetch_logs_for_statuses'   => ['failed', 'canceled'],
        'fetch_success_logs'        => false,              // logs of green jobs are noise
    ],

    'analysis' => [
        'auto_analyze'          => true,
        'min_confidence_to_show'=> 0.40,
        'cache_ttl_hours'       => 168,          // 7 days: same signature = same answer
        'max_similar_failures'  => 5,
        'similarity_threshold'  => 0.75,
    ],

    'retention' => [
        'pipeline_events_days' => 30,
        'commit_changes_days'  => 90,
        'activity_logs_days'   => 90,
        'ai_requests_days'     => 180,
        'raw_logs_days'        => 90,
    ],

    // path patterns → commit_changes.is_config / is_dependency
    'file_signals' => [
        'config' => [
            'docker-compose*.y*ml', 'Dockerfile*', '.env*', '*.ci.y*ml',
            '.gitlab-ci.yml', '.github/workflows/*', 'Jenkinsfile',
            'k8s/*', 'helm/*', 'nginx*.conf', 'php.ini', 'supervisord.conf',
        ],
        'dependency' => [
            'package.json', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock',
            'composer.json', 'composer.lock', 'requirements*.txt', 'pyproject.toml',
            'poetry.lock', 'go.mod', 'go.sum', 'Gemfile*', 'pom.xml', 'build.gradle*',
        ],
    ],
];
```

- [ ] `config/pipemind.php` created

---

## 3.3 Migrations

Generate in the exact order from file 02 §Migration order. One migration per table.

> **Do not rely on `make:migration` timestamps for ordering.** They are
> second-granular, and a loop creates collisions — several migrations land on the
> same timestamp and Laravel then orders them alphabetically, which is not
> dependency order. Name them with an explicit sequence instead:
> `2026_01_01_000007_create_projects_table.php`. The prefix is arbitrary; the
> sequence is what matters.

```bash
# ready — generates them pre-ordered by timestamp
for t in create_teams_table \
         add_current_team_to_users_table \
         create_team_user_table \
         create_team_invitations_table \
         create_integrations_table \
         create_projects_table \
         create_pipelines_table \
         create_pipeline_stages_table \
         create_pipeline_jobs_table \
         create_pipeline_events_table \
         create_commit_changes_table \
         create_failure_signatures_table \
         create_failures_table \
         create_analyses_table \
         create_analysis_evidence_table \
         create_recommendations_table \
         create_analysis_feedback_table \
         create_remediation_policies_table \
         create_remediations_table \
         create_failure_embeddings_table \
         create_knowledge_documents_table \
         create_knowledge_chunks_table \
         create_project_metrics_daily_table \
         create_job_baselines_table \
         create_anomalies_table \
         create_ai_providers_table \
         create_ai_requests_table \
         create_notification_channels_table \
         create_activity_logs_table \
         create_job_logs_table \
         add_late_foreign_keys_to_projects_table ; do
  php artisan make:migration "$t"
  sleep 1
done
```

### Enable pgvector first

```php
// ready — database/migrations/0000_00_00_000000_enable_extensions.php (rename to be first)
public function up(): void
{
    DB::statement('CREATE EXTENSION IF NOT EXISTS vector');
    DB::statement('CREATE EXTENSION IF NOT EXISTS pg_trgm');
    DB::statement('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"');
}
```

### Migration patterns — copy these three, the rest follow

```php
// ready — pattern A: tenant-scoped table with checked enum + partial index
Schema::create('failures', function (Blueprint $table) {
    $table->id();
    $table->uuid('uuid')->unique()->default(DB::raw('uuid_generate_v4()'));
    $table->foreignId('team_id')->constrained()->cascadeOnDelete();
    $table->foreignId('project_id')->constrained()->cascadeOnDelete();
    $table->foreignId('pipeline_id')->constrained('pipelines')->cascadeOnDelete();
    $table->foreignId('job_id')->nullable()->constrained('pipeline_jobs')->nullOnDelete();
    $table->foreignId('signature_id')->nullable()->constrained('failure_signatures')->nullOnDelete();

    $table->string('status', 20)->default('detected');
    $table->string('severity', 10)->default('medium');
    $table->string('category', 30)->default('UNKNOWN');
    $table->string('subcategory', 60)->nullable();
    $table->string('stage_name', 120)->nullable();
    $table->string('job_name', 190)->nullable();
    $table->text('error_message')->nullable();
    $table->string('error_type', 120)->nullable();
    $table->smallInteger('exit_code')->nullable();
    $table->boolean('is_flaky')->default(false);
    $table->boolean('is_transient')->default(false);
    $table->integer('occurrence_index')->default(1);

    $table->timestampTz('failed_at');
    $table->timestampTz('detected_at')->useCurrent();
    $table->timestampTz('resolved_at')->nullable();
    $table->foreignId('resolved_by')->nullable()->constrained('users')->nullOnDelete();
    $table->string('resolution_type', 20)->nullable();
    $table->text('resolution_note')->nullable();
    $table->string('resolution_commit_sha', 64)->nullable();
    $table->integer('time_to_resolution_seconds')->nullable();
    $table->timestampsTz();

    $table->index(['project_id', 'failed_at'], 'idx_failures_project_failed');
    $table->index(['team_id', 'status'], 'idx_failures_team_status');
    $table->index(['project_id', 'category', 'failed_at'], 'idx_failures_category');
});

// CHECK constraints and partial indexes need raw SQL — Laravel's builder can't express them
DB::statement("ALTER TABLE failures ADD CONSTRAINT chk_failures_status
    CHECK (status IN ('detected','queued','analyzing','analyzed','analysis_failed','resolved','ignored'))");
DB::statement("ALTER TABLE failures ADD CONSTRAINT chk_failures_severity
    CHECK (severity IN ('low','medium','high','critical'))");
DB::statement("CREATE INDEX idx_failures_unresolved ON failures(project_id, failed_at DESC)
    WHERE resolved_at IS NULL");
```

```php
// ready — pattern B: vector column + HNSW index
Schema::create('failure_embeddings', function (Blueprint $table) {
    $table->id();
    $table->foreignId('failure_id')->constrained()->cascadeOnDelete();
    $table->foreignId('signature_id')->nullable()->constrained('failure_signatures')->cascadeOnDelete();
    $table->foreignId('team_id')->constrained()->cascadeOnDelete();
    $table->string('model', 120)->default('all-MiniLM-L6-v2');
    $table->smallInteger('dimensions')->default(384);
    $table->text('source_text');
    $table->timestampTz('created_at')->useCurrent();
    $table->unique(['failure_id', 'model']);
});

DB::statement('ALTER TABLE failure_embeddings ADD COLUMN embedding vector(384) NOT NULL');
DB::statement('CREATE INDEX idx_failure_embeddings_hnsw ON failure_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)');
```

```php
// ready — pattern C: late FKs breaking the projects ↔ ai_providers ↔ pipelines cycle
Schema::table('projects', function (Blueprint $table) {
    $table->foreign('ai_provider_id')->references('id')->on('ai_providers')->nullOnDelete();
    $table->foreign('last_pipeline_id')->references('id')->on('pipelines')->nullOnDelete();
});
```

- [ ] All 31 migrations written to match file 02 exactly
- [ ] `php artisan migrate:fresh` runs clean
- [ ] `php artisan migrate:rollback` unwinds without error (test your `down()` methods)

### Schema drift guard

```php
// spec — app/Console/Commands/SchemaCheck.php
// Dumps the live schema (tables + columns + types) and diffs it against
// PipeMind-data/database/schema.sql. Non-zero exit on drift.
// Wire into CI in file 22. This is what stops the docs from becoming fiction.
```

- [ ] `php artisan pipemind:schema-check` implemented and passing

---

## 3.4 Models

```bash
# ready
php artisan make:model Team
php artisan make:model TeamInvitation
php artisan make:model Integration
php artisan make:model Project
php artisan make:model Pipeline
php artisan make:model PipelineStage
php artisan make:model PipelineJob
php artisan make:model PipelineEvent
php artisan make:model JobLog
php artisan make:model CommitChange
php artisan make:model FailureSignature
php artisan make:model Failure
php artisan make:model Analysis
php artisan make:model AnalysisEvidence
php artisan make:model AnalysisFeedback
php artisan make:model Recommendation
php artisan make:model Remediation
php artisan make:model RemediationPolicy
php artisan make:model FailureEmbedding
php artisan make:model KnowledgeDocument
php artisan make:model KnowledgeChunk
php artisan make:model ProjectMetricDaily
php artisan make:model JobBaseline
php artisan make:model Anomaly
php artisan make:model AiProvider
php artisan make:model AiRequest
php artisan make:model NotificationChannel
php artisan make:model ActivityLog
```

### Shared concerns

```php
// ready — app/Models/Concerns/HasUuid.php
namespace App\Models\Concerns;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Str;

trait HasUuid
{
    protected static function bootHasUuid(): void
    {
        static::creating(function ($model) {
            if (empty($model->uuid)) {
                $model->uuid = (string) Str::uuid();
            }
        });
    }

    public function getRouteKeyName(): string
    {
        return 'uuid';
    }

    public function scopeByUuid(Builder $q, string $uuid): Builder
    {
        return $q->where('uuid', $uuid);
    }
}
```

```php
// ready — app/Models/Concerns/BelongsToTeam.php
namespace App\Models\Concerns;

use App\Models\Team;
use App\Scopes\TeamScope;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

trait BelongsToTeam
{
    protected static function bootBelongsToTeam(): void
    {
        static::addGlobalScope(new TeamScope);

        static::creating(function ($model) {
            if (empty($model->team_id) && $teamId = currentTeamId()) {
                $model->team_id = $teamId;
            }
        });
    }

    public function team(): BelongsTo
    {
        return $this->belongsTo(Team::class);
    }
}
```

```php
// ready — app/Scopes/TeamScope.php
namespace App\Scopes;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Scope;

class TeamScope implements Scope
{
    public function apply(Builder $builder, Model $model): void
    {
        // Queue workers and webhooks run without a session — they set the team explicitly.
        if ($teamId = currentTeamId()) {
            $builder->where($model->getTable().'.team_id', $teamId);
        }
    }
}
```

```php
// ready — app/Support/helpers.php  (autoload via composer.json "files")
use App\Models\Team;

function currentTeamId(): ?int
{
    return app()->bound('pipemind.team')
        ? app('pipemind.team')?->id
        : auth()->user()?->current_team_id;
}

function currentTeam(): ?Team
{
    return app()->bound('pipemind.team') ? app('pipemind.team') : auth()->user()?->currentTeam;
}

/** Run a closure bound to a team — used by every queued job. */
function withTeam(Team $team, callable $fn): mixed
{
    app()->instance('pipemind.team', $team);
    try {
        return $fn();
    } finally {
        app()->forgetInstance('pipemind.team');
    }
}
```

> **Every queued job must wrap its work in `withTeam()`.** A worker has no authenticated user, so the global scope would silently return everything. This is the single most likely source of a cross-tenant data leak in the whole application — make it a code-review checklist item.

### Relationship map

```php
// spec — implement exactly these
User:      teams() BelongsToMany(Team, 'team_user')->withPivot('role')
           currentTeam() BelongsTo(Team)
           ownedTeams() HasMany(Team, 'owner_id')

Team:      owner() BelongsTo(User) · users() BelongsToMany(User)->withPivot('role')
           invitations() HasMany · integrations() HasMany · projects() HasMany
           aiProviders() HasMany · failureSignatures() HasMany · notificationChannels() HasMany
           remediationPolicies() HasMany · activityLogs() HasMany · aiRequests() HasMany

Integration: team() BelongsTo · projects() HasMany · events() HasMany(PipelineEvent)
             creator() BelongsTo(User,'created_by')

Project:   team() BelongsTo · integration() BelongsTo · aiProvider() BelongsTo
           pipelines() HasMany · lastPipeline() BelongsTo(Pipeline,'last_pipeline_id')
           failures() HasMany · anomalies() HasMany · metrics() HasMany(ProjectMetricDaily)
           baselines() HasMany(JobBaseline) · knowledgeDocuments() HasMany
           jobs() HasManyThrough(PipelineJob, Pipeline)

Pipeline:  project() BelongsTo · stages() HasMany->orderBy('position')
           jobs() HasMany(PipelineJob)->orderBy('position')
           failedJobs() HasMany(PipelineJob)->where('status','failed')
           failures() HasMany · changes() HasMany(CommitChange) · events() HasMany(PipelineEvent)
           retryOf() BelongsTo(self,'retry_of_id') · retries() HasMany(self,'retry_of_id')

PipelineJob: pipeline() BelongsTo · stage() BelongsTo(PipelineStage)
             log() HasOne(JobLog) · failure() HasOne(Failure,'job_id')

Failure:   project() BelongsTo · pipeline() BelongsTo · job() BelongsTo(PipelineJob)
           signature() BelongsTo(FailureSignature)
           analyses() HasMany->latest() · latestAnalysis() HasOne(Analysis)->latestOfMany()
           recommendations() HasMany · remediations() HasMany
           embedding() HasOne(FailureEmbedding) · resolver() BelongsTo(User,'resolved_by')

Analysis:  failure() BelongsTo · evidence() HasMany(AnalysisEvidence)->orderBy('position')
           recommendations() HasMany->orderBy('position') · feedback() HasMany(AnalysisFeedback)

Recommendation: analysis() BelongsTo · failure() BelongsTo · remediation() HasOne

Remediation: failure() BelongsTo · recommendation() BelongsTo · project() BelongsTo
             requester()/approver()/rejecter() BelongsTo(User) · resultingPipeline() BelongsTo(Pipeline)

FailureSignature: team() BelongsTo · failures() HasMany · embeddings() HasMany(FailureEmbedding)

KnowledgeDocument: chunks() HasMany(KnowledgeChunk)->orderBy('chunk_index')
```

### Casts — get these right or you'll debug them for a week

```php
// ready — Integration
protected function casts(): array
{
    return [
        'credentials'      => 'encrypted:array',   // never plain
        'scopes'           => 'array',
        'settings'         => 'array',
        'last_verified_at' => 'immutable_datetime',
        'last_event_at'    => 'immutable_datetime',
    ];
}

// ready — AiProvider
protected $hidden = ['api_key'];
protected function casts(): array
{
    return [
        'api_key'            => 'encrypted',
        'settings'           => 'array',
        'is_default'         => 'boolean',
        'is_local'           => 'boolean',
        'temperature'        => 'float',
        'input_cost_per_1k'  => 'decimal:6',
        'output_cost_per_1k' => 'decimal:6',
    ];
}

// ready — Analysis
protected function casts(): array
{
    return [
        'confidence'                => 'float',
        'classification_confidence' => 'float',
        'cost_usd'                  => 'decimal:6',
        'raw_response'              => 'array',
        'used_rag'                  => 'boolean',
        'cache_hit'                 => 'boolean',
        'is_transient'              => 'boolean',
        'retry_recommended'         => 'boolean',
        'started_at'                => 'immutable_datetime',
        'completed_at'              => 'immutable_datetime',
    ];
}

// ready — Project
protected function casts(): array
{
    return [
        'tech_stack'          => 'array',
        'analyze_on_branches' => 'array',
        'settings'            => 'array',
        'is_active'           => 'boolean',
        'auto_analyze'        => 'boolean',
        'success_rate'        => 'float',
        'last_pipeline_at'    => 'immutable_datetime',
    ];
}
```

- [ ] All 28 models created with `HasUuid` / `BelongsToTeam` where applicable
- [ ] All relationships implemented
- [ ] `$hidden` set on `Integration` (credentials, webhook_secret), `AiProvider` (api_key), `NotificationChannel` (config)

### Enums as PHP enums

```php
// ready — app/Enums/FailureCategory.php
namespace App\Enums;

enum FailureCategory: string
{
    case BUILD          = 'BUILD';
    case TEST           = 'TEST';
    case DEPENDENCY     = 'DEPENDENCY';
    case DATABASE       = 'DATABASE';
    case NETWORK        = 'NETWORK';
    case DOCKER         = 'DOCKER';
    case DEPLOYMENT     = 'DEPLOYMENT';
    case CONFIGURATION  = 'CONFIGURATION';
    case AUTHENTICATION = 'AUTHENTICATION';
    case PERMISSION     = 'PERMISSION';
    case INFRASTRUCTURE = 'INFRASTRUCTURE';
    case RESOURCE       = 'RESOURCE';
    case UNKNOWN        = 'UNKNOWN';

    /** Must match 00-INDEX.md category colors exactly — the frontend reads this from the API. */
    public function color(): string
    {
        return match ($this) {
            self::DATABASE       => '#A9E831',
            self::TEST           => '#F04438',
            self::DEPENDENCY     => '#F5A524',
            self::DOCKER         => '#38BDF8',
            self::NETWORK        => '#6366F1',
            self::BUILD          => '#EC4899',
            self::DEPLOYMENT     => '#14B8A6',
            self::CONFIGURATION  => '#A855F7',
            self::AUTHENTICATION => '#F97316',
            self::PERMISSION     => '#8B5CF6',
            self::INFRASTRUCTURE => '#0EA5E9',
            self::RESOURCE       => '#EAB308',
            self::UNKNOWN        => '#5C6472',
        };
    }

    public function label(): string
    {
        return ucfirst(strtolower($this->name));
    }
}
```

Also create: `PipelineStatus`, `JobStatus`, `FailureSeverity`, `TeamRole`, `ActionType`, `RiskLevel`, `RemediationStatus`, `ProviderType`, `AnalysisStatus`, `ActivityAction`.

- [ ] 11 enum classes created, referenced in model casts

---

## 3.5 Queues & Horizon

```php
// ready — config/horizon.php → defaults
'defaults' => [
    'ingestion' => [
        'connection' => 'redis',
        'queue'      => ['ingestion'],
        'balance'    => 'auto',
        'maxProcesses' => 6,
        'tries'      => 3,
        'timeout'    => 120,
    ],
    'logs' => [
        'connection' => 'redis',
        'queue'      => ['logs'],
        'balance'    => 'auto',
        'maxProcesses' => 4,
        'tries'      => 3,
        'timeout'    => 300,      // large log downloads
        'memory'     => 512,
    ],
    'analysis' => [
        'connection' => 'redis',
        'queue'      => ['analysis'],
        'balance'    => 'auto',
        'maxProcesses' => 3,      // deliberately low — LLM rate limits
        'tries'      => 2,
        'timeout'    => 180,
    ],
    'default' => [
        'connection' => 'redis',
        'queue'      => ['default','notifications','metrics'],
        'balance'    => 'auto',
        'maxProcesses' => 4,
        'tries'      => 3,
        'timeout'    => 90,
    ],
],
```

**Queue routing table** — every job declares its queue in the constructor:

| Queue | Jobs | Why separate |
|---|---|---|
| `ingestion` | `ProcessPipelineEvent`, `SyncPipeline`, `SyncJobs` | Must stay fast; webhooks time out |
| `logs` | `FetchJobLog`, `StoreJobLog`, `ProcessJobLog` | Slow, memory-hungry, network-bound |
| `analysis` | `AnalyzeFailure`, `EmbedFailure`, `GenerateRecommendations` | Rate-limited by the LLM provider |
| `notifications` | `SendSlackNotification`, `SendFailureEmail` | Failure here must not block analysis |
| `metrics` | `RollupProjectMetrics`, `ComputeJobBaselines`, `DetectAnomalies` | Scheduled, low priority |
| `default` | everything else | — |

- [ ] Horizon config set, `php artisan horizon` runs, dashboard at `/horizon`
- [ ] `HorizonServiceProvider::gate()` restricts the dashboard to team owners in non-local envs

### Scheduler

```php
// ready — routes/console.php  (Laravel 12 style)
use Illuminate\Support\Facades\Schedule;

Schedule::command('pipemind:refresh-project-stats')->everyFiveMinutes();
Schedule::command('pipemind:rollup-metrics')->hourlyAt(5);
Schedule::command('pipemind:compute-baselines')->dailyAt('03:00');
Schedule::command('pipemind:detect-anomalies')->everyTenMinutes();
Schedule::command('pipemind:reconcile-pipelines')->everyFifteenMinutes();  // catch missed webhooks
Schedule::command('pipemind:prune')->dailyAt('04:00');
Schedule::command('horizon:snapshot')->everyFiveMinutes();
```

> `pipemind:reconcile-pipelines` polls the provider for pipelines stuck in `running` for longer than their project's p95 duration. Webhooks *will* be lost — a network blip, a restart, a provider outage. Reconciliation is not optional; without it your UI shows spinners forever.

- [ ] Six commands stubbed (implementations land in files 05, 10, 19)

---

## 3.6 Factories & seeders

Factories are not just for tests — they generate your demo workspace and your synthetic training data.

```php
// ready — database/factories/PipelineFactory.php (the important one)
public function definition(): array
{
    $started  = fake()->dateTimeBetween('-30 days', 'now');
    $duration = fake()->numberBetween(45, 480);

    return [
        'external_id'      => (string) fake()->unique()->numberBetween(10000, 99999),
        'iid'              => fake()->unique()->numberBetween(1, 999),
        'provider'         => 'gitlab',
        'status'           => 'success',
        'source'           => fake()->randomElement(['push','merge_request','schedule']),
        'ref'              => fake()->randomElement(['main','feature/payment','feature/auth','bugfix/db-conn']),
        'commit_sha'       => fake()->sha1(),
        'commit_short_sha' => substr(fake()->sha1(), 0, 8),
        'commit_message'   => fake()->sentence(6),
        'commit_author_name'  => fake()->name(),
        'commit_author_email' => fake()->safeEmail(),
        'started_at'       => $started,
        'finished_at'      => (clone $started)->modify("+{$duration} seconds"),
        'duration_seconds' => $duration,
        'queue_seconds'    => fake()->numberBetween(0, 30),
        'jobs_total'       => 6,
        'jobs_succeeded'   => 6,
    ];
}

public function failed(): static
{
    return $this->state(fn () => [
        'status'         => 'failed',
        'has_failure'    => true,
        'jobs_failed'    => 1,
        'jobs_succeeded' => 5,
    ]);
}

public function running(): static
{
    return $this->state(fn () => [
        'status'      => 'running',
        'finished_at' => null,
        'duration_seconds' => null,
    ]);
}
```

### The demo seeder

This must produce exactly what `ui/workspace.png` and `ui/project.png` show. Build the frontend against it before any real ingestion exists.

```php
// spec — database/seeders/DemoSeeder.php
// 1. User: Oussema <jbelioussema33@gmail.com>, password "123456789az", role owner
// 2. Team: "OJ Team", plan free, privacy_mode cloud_redacted
// 3. Integration: GitLab @ http://gitlab.local, status active
// 4. AiProvider: Gemini Flash, is_default, with realistic per-1k costs
// 5. Four projects matching the mockup exactly:
//      biker-api    Laravel · Docker · GitHub   98% · 2 failures today · 124 pipelines
//      biker-front  Vue · TypeScript · GitHub   94% · 1 failure today  ·  87 pipelines
//      biker-mobile React Native · Docker · GitHub 91% · 3 failures today · 63 pipelines
//      biker-admin  Laravel · Docker · GitHub   97% · 0 failures today ·  56 pipelines
// 6. Per project: 60 days of pipelines at the stated success rate, 6 jobs each,
//    stages: checkout → install → lint → test → build → deploy
// 7. Failures across all 13 categories, weighted realistically:
//      TEST 24% · DEPENDENCY 22% · DATABASE 16% · DOCKER 12% · NETWORK 9%
//      CONFIGURATION 7% · BUILD 5% · others 5%
//    Each with a real-looking error_message from taxonomy/failure-categories.md
// 8. For ~70% of failures: a completed Analysis with 3–5 evidence rows
//    and 2–3 recommendations, confidence 0.72–0.96
// 9. 30% of failures resolved, with time_to_resolution 5–45 min → MTTR tile shows ~18m
// 10. failure_signatures deduplicated; 5 marked is_known with a resolution
// 11. project_metrics_daily backfilled for 60 days (charts need real history)
// 12. 40 activity_logs across the action vocabulary, last 6 hours
// 13. 3 open anomalies (one duration 4.1×, one memory, one failure_rate)
// 14. 2 pending_approval remediations
// 15. Default remediation_policies for the team (the 9 rows from file 02)
```

```php
// ready — database/seeders/DatabaseSeeder.php
public function run(): void
{
    $this->call([
        FailureTaxonomySeeder::class,   // static reference data
        DemoSeeder::class,
    ]);
}
```

- [ ] All factories written
- [ ] `DemoSeeder` produces the mockup numbers
- [ ] `php artisan migrate:fresh --seed` completes in < 30 s

> **Do not skip the 60-day metric backfill.** Every chart on the project board — Pipeline Activity, Success Rate, the sparklines on all five KPI tiles — needs history. Without it you build the frontend against empty arrays and discover the layout breaks on real data.

---

## 3.7 Sanity checks

```php
// ready — tests/Feature/SchemaTest.php
it('has all expected tables', function () {
    $expected = ['users','teams','team_user','team_invitations','integrations','projects',
        'pipelines','pipeline_stages','pipeline_jobs','pipeline_events','job_logs',
        'commit_changes','failure_signatures','failures','analyses','analysis_evidence',
        'analysis_feedback','recommendations','remediations','remediation_policies',
        'failure_embeddings','knowledge_documents','knowledge_chunks','project_metrics_daily',
        'job_baselines','anomalies','ai_providers','ai_requests','notification_channels',
        'notifications','activity_logs'];

    foreach ($expected as $table) {
        expect(Schema::hasTable($table))->toBeTrue("missing table: {$table}");
    }
});

it('scopes queries to the current team', function () {
    [$teamA, $teamB] = Team::factory()->count(2)->create();
    Project::factory()->for($teamA)->create();
    Project::factory()->for($teamB)->create();

    withTeam($teamA, fn () => expect(Project::count())->toBe(1));
});

it('never exposes integration credentials', function () {
    $i = Integration::factory()->create(['credentials' => ['token' => 'secret-value']]);
    expect($i->toArray())->not->toHaveKey('credentials')
        ->and(json_encode($i))->not->toContain('secret-value');
});
```

- [ ] Three tests pass

### Test database

`RefreshDatabase` must run against **PostgreSQL**, not the sqlite default — the
schema uses `vector`, `gin_trgm_ops` and partial indexes that sqlite cannot express.
Create a separate database and point `phpunit.xml` at it:

```bash
# ready
psql -h 127.0.0.1 -p 5434 -U pipemind -d postgres -c "CREATE DATABASE pipemind_test OWNER pipemind"
```

```xml
<!-- ready — phpunit.xml <php>, replacing the sqlite defaults -->
<env name="DB_CONNECTION" value="pgsql"/>
<env name="DB_DATABASE" value="pipemind_test"/>
<env name="DB_PORT" value="5434"/>
<env name="REDIS_CLIENT" value="predis"/>
<env name="REDIS_PORT" value="6380"/>
```

Remove the `DB_CONNECTION=sqlite` and `DB_DATABASE=:memory:` lines Laravel ships
with, or they win over `.env.testing`.

---

## Definition of Done

```bash
make fresh                      # migrate:fresh --seed, clean
php artisan test                # SchemaTest green
php artisan horizon             # boots, /horizon reachable
php artisan tinker --execute="echo App\Models\Project::withoutGlobalScopes()->count();"   # 4
php artisan tinker --execute="echo App\Models\Pipeline::withoutGlobalScopes()->count();"  # ~330
php artisan tinker --execute="echo App\Models\Failure::withoutGlobalScopes()->count();"   # ~25
```

- [ ] All commands succeed
- [ ] `pipemind:schema-check` reports no drift from `PipeMind-data/database/schema.sql`

**Next:** [`04-backend-auth-api.md`](04-backend-auth-api.md)
