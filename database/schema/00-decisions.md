# Architecture Decisions

Locked in file 01. Each entry records the choice, the reason, and what it would cost to reverse.

| Date | Decision | Choice | Reason | Reversibility |
|---|---|---|---|---|
| 2026-08-30 | Embedding model | `all-MiniLM-L6-v2`, **384 dim** | CPU-only, no API key, ~90 MB, adequate for error text | **Hard** — fixes the `vector(384)` column. Mitigated by `failure_embeddings.model` + `UNIQUE(failure_id, model)`, which allow a second model to be backfilled alongside and compared before cutover. |
| 2026-08-30 | LLM provider | Abstraction over Gemini / OpenAI-compatible / Ollama / stub | Provider independence; the key is not yet available | **Easy** — one env var |
| 2026-08-30 | Starting LLM | `stub` → Gemini when the key arrives | Files 06–16 are fully buildable with no key | Easy |
| 2026-08-30 | Raw log storage | MinIO (S3 API) | Logs run 5–200 MB; Postgres keeps metadata + excerpt only | Medium — a disk swap plus a backfill |
| 2026-08-30 | Multi-tenancy | `team_id` on every tenant table, from day one | Retrofitting tenancy is a rewrite | Not reversible in practice |
| 2026-08-30 | Public identifiers | `uuid` column alongside a `bigint` PK | Do not leak row counts or permit enumeration | Easy |
| 2026-08-30 | Enums | `varchar` + `CHECK` constraint | Taxonomies grow; `ALTER TYPE` locks, a CHECK swap does not | Easy |
| 2026-08-30 | Primary CI platform | GitLab (local CE, or gitlab.com + tunnel) | Plain-text job logs, cleanest API, controllable failures | Easy — the adapter layer isolates it |
| 2026-08-30 | Redis client | `predis` (pure PHP) | `ext-redis` is not installed on the dev machine | Easy — set `REDIS_CLIENT=phpredis` |
| 2026-08-30 | Kafka / Spark | **Not implemented**; documented as a scaling path | Redis queues + Postgres handle this project's volume; the operational cost is not earned | Easy to add later |
| 2026-08-30 | `repositories` table | Folded into `projects` | 1:1 with a project in every supported provider; removes a join from hot queries | Medium |

## Host port allocation

This machine already runs a host PostgreSQL (5432), a host Redis (6379), and other
project containers (`shlink` on 8080, `shlink_db` on 5433, `devorc-postgres` on 5442).
PipeMind therefore publishes on non-default host ports. Container-internal ports are
unchanged, so nothing inside the stack is aware of this.

| Service | Host port | Container port | Note |
|---|---|---|---|
| PostgreSQL | **5434** | 5432 | 5432 host, 5433 shlink_db, 5442 devorc all taken |
| Redis | **6380** | 6379 | 6379 host redis-server |
| MinIO API | 9000 | 9000 | |
| MinIO console | 9001 | 9001 | |
| Mailpit SMTP | 1025 | 1025 | |
| Mailpit UI | 8025 | 8025 | |
| Laravel API | 8000 | — | `php artisan serve` |
| AI service | 8001 | 8001 | |
| Vite dev | 5173 | — | |
| Reverb (file 17) | **8081** | 8080 | 8080 taken by `shlink` |
| GitLab CE (lab) | 8929 | 8929 | started on demand only |
| Ollama (optional) | 11434 | 11434 | |

> Docker Compose reads `DB_PORT` and `REDIS_PORT` from `PipeMind-back/.env` — the same
> file Laravel reads. Host and container therefore cannot drift apart.

**Why this matters:** the first `docker compose up` silently started PostgreSQL *without*
publishing a port, because 5432 was already bound. The container was healthy, but Laravel
would have connected to the host PostgreSQL — no pgvector, no PipeMind schema — and
appeared almost-working while being entirely wrong. Always verify `docker compose ps`
shows a real `PORTS` value, not an empty column.

---

## `similarity_threshold` is 0.55, not 0.75

The roadmap's starting guess of 0.75 returns **zero rows** on realistic CI failures.
Across ten pairs the highest cosine similarity observed was 0.5865, so the guess made
retrieval silently return nothing at all — no error, no log, no failing test, just an
always-empty "similar failures" panel that is indistinguishable from a workspace with
no history yet.

Lowered to 0.55 and marked provisional. Full method, pair matrix and limitations in
[`experiments/similarity-threshold.md`](../../experiments/similarity-threshold.md).

Two settings must be kept in step: `SIMILARITY_THRESHOLD` in `PipeMind-ai/.env` (the
authoritative one, used by the query) and `pipemind.analysis.similarity_threshold` in
Laravel (display only).

## `find_similar_failures` ranks same-category neighbours above closer ones

Ordering is `resolved DESC, same_category DESC, distance`. Embeddings put two Node
failures near each other because they are both Node — in the pair matrix a Node database
error and a Node dependency error scored 0.5865, outranking the genuinely same-cause pair
at 0.5772. Category as a ranking key removes that artefact.

A hard `WHERE category = :category` filter was considered and rejected: a Docker failure
can genuinely present as a database symptom, and a hard filter makes that case unreachable.

## `failures.ecosystem` is stored, not re-derived

The AI service detects the ecosystem while processing a log and folds it into the
signature hash, but nothing persisted it — it was passed to `DetectFailure` and dropped.
At analysis time the embedding therefore could not be composed the same way the signature
was hashed, and retrieval quietly lost a dimension of context.

Added as a column on `failures` rather than on `failure_signatures`, because not every
failure has a signature (a failure with no error text never gets one) and the
embedding path needs the value per failure without a join.

## Tenancy for models with no `team_id`

`pipelines` and `pipeline_jobs` belong to a team only through their project, so `TeamScope`
has no column to filter on. Route model binding would resolve **any** team's UUID — and
`GET /jobs/{job}/log` returns log content, the most sensitive data in the system.

`Concerns\ScopedThroughProject` overrides `resolveRouteBinding` to constrain through the
project relation. Deliberately *not* a global scope: queued jobs and webhook ingestion
legitimately run with no team bound, and a global scope would make them silently return
nothing.

## The cache's warm path must respect feedback

`AnalysisCache::forget()` deletes the Redis key, but `get()` also has a database fallback
that looks for a recent confident analysis of the same signature. Without an exclusion,
purging the cache after a developer marks an analysis wrong achieves nothing — the very
next lookup resurrects the rejected analysis out of `analyses`.

`get()` now excludes any analysis carrying feedback with `was_helpful = false` or
`root_cause_correct = false`.

## `Http::preventStrayRequests()` in `Tests\TestCase`

An unfaked HTTP call used to reach the real network. On a machine running the AI service
on :8001 the suite passed or failed depending on what happened to be running locally —
three ingestion tests were silently talking to the live Python service. Tests that depend
on the outside world are not tests.

## Risk is assigned from `action_type`, in code

`recommender.sanitize()` overwrites whatever risk the model proposed, using the
`ACTION_RISK` table, and escalates one level on the default branch. A model asked politely
to be careful can still label a production rollback "low risk"; the policy engine that
decides what runs automatically must not depend on that politeness.

A test asserts `ACTION_RISK`'s keys equal the schema's `action_type` enum, because drift
there is silent: an action the schema allows but the table does not know degrades to
`manual` and quietly discards what the model proposed.

---

## `"rate" in message` matched inside `GenerateContent`

`GeminiProvider._translate` classified errors by substring, and tested `"rate"`
before anything else. Gemini names the method `GenerativeService.GenerateContent`
in every error it returns — so `"rate"` matched inside `gene**rate**content`, and
**every** Gemini failure was reported as a rate limit.

Rate limits are retryable, so a wrong API key was retried three times with
exponential backoff, then surfaced to the user as `AI_PROVIDER_RATE_LIMITED`.
The real cause — a credential of the wrong type — never reached the screen.

Fixed by checking authentication first and by using precise tokens
(`"rate limit"`, `"rate_limit"`, `"429"`, `"quota"`, `"resource_exhausted"`).

The unit test that was supposed to cover this had passed, because its synthetic
error message omitted the `GenerateContent` substring that caused the bug.
`tests/unit/test_provider_verify.py` now pins **Google's verbatim 401 body** as a
constant — a paraphrased fixture is what let this through.

## `LLMAuthenticationFailed` is separate from `LLMUnavailable`

A rejected credential is a configuration mistake only a human can fix, not an
outage. As `LLMUnavailable` it was retryable, so one typo passed through three
layers of retry — tenacity, the fallback provider, then the queue — producing
nine useless calls and burying the one message worth reading.

`AI_PROVIDER_UNAUTHORIZED` / 401 / `retryable = False`, mapped in Laravel to
`AiProviderUnauthorized` and caught explicitly in `AnalyzeFailure`.

## Providers are tested before they are saved

`POST /v1/ai-providers/test` (Laravel) → `POST /v1/providers/test` (AI service) →
`provider.verify()`. The same contract the integration wizard already uses: prove
the connection works, then persist. `store()` and `update()` refuse to save a
provider that fails the check.

`verify()` lists models rather than generating: it costs no tokens, needs no
quota, and separates "the key is wrong" from "the model name is wrong" — which a
generate call cannot. For Ollama it answers the local equivalent: is the server
running, and is the model actually pulled?

The test path passes `allow_env_fallback=False`. Without it, testing a provider
with no key silently borrowed the server's own `GEMINI_API_KEY` and reported
success for a credential the user never entered.

## The seeded default must actually work

`DemoSeeder` seeded a keyless Gemini provider as the team default, with
`status = 'active'` and `last_tested_at = now()` — a claim nothing had ever
tested. Every analysis in a fresh workspace therefore failed with "No Gemini API
key configured", which reads as a broken application rather than an unfinished
setup. The seeder's own comment said the stub should be the default; the code did
the opposite.

The stub is now the default (it is the only provider that can honestly claim to
work with no key). Gemini is seeded alongside it as `untested`, with
`last_error` naming the next step, so the workspace shows what to configure
without pretending it already works.

---

## `AQ.Ab8…` is a valid Google AI Studio API key

An earlier version of this file, and the provider's error message, claimed
otherwise. That was wrong. Google issues API keys in two shapes — the older
`AIzaSy…` (39 chars) and the newer `AQ.Ab8…` (53) — and both work against
`generativelanguage.googleapis.com`.

The confusion came from Google's own error. A key of the newer format with **one
stray character** returns:

```
401 UNAUTHENTICATED · reason: ACCESS_TOKEN_TYPE_UNSUPPORTED
"Expected OAuth 2 access token, login cookie or other valid authentication credential"
```

That reason code blames the credential *type*, so a truncated paste looks exactly
like the wrong kind of credential. The message now points at a bad copy instead of
sending the user off to regenerate a key that was never the problem.

**Do not validate API keys by prefix or length.** Google has changed both.

## `ListModels` is not evidence a model can be called

`verify()` originally checked the model against `ListModels` and reported
"Connected. 40 models available." for `gemini-2.5-flash`. The first real analysis
then failed:

```
404 NOT_FOUND — This model models/gemini-2.5-flash is no longer available to new
users. Please update your code to use models/gemini-3.6-flash
```

The model was listed and uncallable. Verifying against the list produced exactly
the false confidence the endpoint exists to prevent.

`verify()` now fetches the list for the model picker but decides `ok` with a real
one-token generation. Seven input tokens is a rounding error against shipping a
provider that fails on its first real analysis. It also parses Google's
replacement model out of the 404 and passes it through, so the message names the
fix.

The default model is `gemini-3.6-flash`; the whole 2.5 family is retired for
newly issued keys.

## Thinking tokens are the latency, and they are billed

Gemini 3.x reasons before answering. Measured on one fixture: `high` = 16.4 s /
2330 thinking tokens, unset = 11.1 s / 1462, `low` = 3.2 s / 0 — all producing
valid JSON.

`GEMINI_THINKING_LEVEL=low` is the default. CI failure analysis is
short-context and heavily grounded, and the rule classifier has already narrowed
the category, so the extra reasoning buys little.

Thinking tokens never appear in the response but **are billed as output**.
`GeminiProvider` adds `thoughts_token_count` into `completion_tokens`; without
it every cost figure in the reports was understated by roughly 4×.

## The embedder loads at boot, not on first use

sentence-transformers takes ~6.9 s to load. Lazily, that landed on the first real
analysis after every restart — 13.9 s end to end against 4.0 s warm. It reads as
a slow model rather than a cold start, and it is the single worst number a
reviewer would have seen.

`main.py`'s lifespan warms it and logs `embedder_warm_ms`. Failure there is not
fatal: retrieval degrades to nothing via `retrieve_safely`, and classification
plus a cloud LLM still work. A service that refuses to boot because an optional
extra is missing is worse than a slow one.

## `value()` applies casts, and enums do not survive JSON

`AnalysisContextBuilder::previousStatus()` declared `?string` and returned
`$query->value('status')` — which Eloquent casts to a `PipelineStatus` enum. Every
failure whose branch had a prior pipeline died with a `TypeError` before any HTTP
call. The first failure analysed had no prior pipeline, so it returned null and
the bug stayed invisible until a batch run across categories.

The payload crosses a service boundary as JSON, so anything leaving the context
builder must be a scalar.

---

## Free-tier quota is the real ceiling, not the monthly budget

Google's free tier caps `generateContent` at **20 requests per day, per model**:

```
429 RESOURCE_EXHAUSTED
quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
quotaValue: 20   model: gemini-3.6-flash
```

At a measured $0.0015 per analysis, a $25 monthly budget would allow ~16 000
analyses. The daily free-tier limit stops things at 20. **The budget guard will
essentially never fire on the free tier** — the quota gets there first, every
time. Worth stating plainly rather than presenting the budget ceiling as the
operative constraint.

Practical consequence for demos and evaluation: 20 analyses per day. Use
`--force` sparingly, lean on the analysis cache (a repeat is free and does not
touch the quota), and switch a project to the `stub` provider while working on
anything that is not the LLM path.

## A rate limit is not an outage

`AI_PROVIDER_RATE_LIMITED` fell through `AiGateway`'s `match` to the `default`
arm and surfaced as `AiServiceUnavailable` — "The analysis service is
unreachable." A user who has simply spent the day's quota would go and check
containers and logs for a problem that does not exist.

`AiProviderRateLimited` (429, retryable) is now mapped explicitly and caught in
`AnalyzeFailure`, which records `ai_requests.status = 'rate_limited'` and leaves
the failure as `analyzing` between attempts rather than flickering it to failed
for what is only a wait.

## Cache hits report zero latency, not the original call's

`persistCached` zeroed cost and tokens but carried `latency_ms` forward from the
cached payload, so a cache hit reported the same 6.9 s as the model call it
replaced. Every "the cache saved us" figure in the reports would have said the
opposite of the truth. Latency is now zeroed alongside cost.

## `env_file=".env"` resolves against the working directory

Starting uvicorn from the Laravel directory made pydantic-settings load
*Laravel's* `.env`. The service booted with a `DATABASE_URL` SQLAlchemy could not
parse and returned 500 on `/v1/analyze` — which reads as a broken endpoint, not a
misconfiguration.

`Settings.model_config` now anchors `env_file` to the package directory, so the
service finds its own config wherever it is launched from.

---

## No Vue component had ever been unit-tested

`vitest.config.ts` loaded only the `vue()` plugin, while the app depends on
`unplugin-auto-import` for `ref`, `computed`, `useRouter` and every composable.
Mounting any real component therefore failed with `ref is not defined` — which is
why the only frontend tests were pure-function ones.

The vitest config now mirrors the app's plugin set. That is what made testing
`LogViewer` possible at all, and it unblocks component testing across the whole
frontend rather than just this file.

Three jsdom gaps needed shimming in `tests/setup.ts`, and one of them mattered:

- `Element.scrollTo` / `scrollIntoView` — absent in jsdom, present everywhere real.
- **`ResizeObserver` must report an actual size.** jsdom lays nothing out, so
  every element measures 0×0. A no-op shim made the virtualised log render *zero*
  rows — and the test passed vacuously while proving the opposite of its own
  claim. The shim now reads the element's inline height and reports it.

The setup file is guarded for `typeof Element !== 'undefined'`, because it also
loads for node-environment specs.

## The log viewer is virtualised

A full CI log runs to tens of thousands of lines. One table row per line is
~100 000 DOM nodes; the tab stops responding long before the reader finds
anything. `useVirtualList` bounds the rendered rows to the viewport, and a test
asserts the property directly: a 48 000-line log renders **the same node count**
as a 200-line one.

## The frontend contract test must not use `VITE_API_URL`

`.env` sets `VITE_API_URL=/api/v1` — a relative path, correct for the browser's
dev proxy. Node's `fetch` cannot resolve a relative URL, so the contract test
threw, `skipIf` swallowed it, and the file skipped silently — indistinguishable
from "the backend is not running", which is precisely the condition the test
exists to detect. It reads `PM_API_URL` instead, defaulting to an absolute
localhost URL.

That file also needs `// @vitest-environment node`: jsdom enforces CORS on fetch,
so a request to the local API from an `about:blank` document is blocked.

## `policy` is absent until roadmap 18

Recommendations carry no policy decision yet — the remediation policy engine is
file 18. `RecommendationCard` renders the action and its risk, then stops, and
says the change must be applied manually.

Rendering an Apply button without a policy would offer an action the backend
cannot honour. Defaulting the missing field to `auto_allowed` would be worse
still: it would show the safest-looking gate precisely where no gate exists.

---

## `latestOfMany()` needs table-qualified column selection

`Failure::latestAnalysis()` uses `latestOfMany()`, which builds a self-join on
`analyses`. Selecting bare column names against it —
`with('latestAnalysis:id,failure_id,confidence')` — raises
`column reference "failure_id" is ambiguous`.

This caught me twice in one session, in `FailureController` and again in
`PipelineController`, because it only fails on the eager-load path: any test that
does not eager-load passes, and the browser gets a 500. The warning now lives on
the relation itself rather than in whichever controller was written last.

## File 16's remaining views needed backend that did not exist

Pipelines list, pipeline detail, analyses and failure history all read endpoints
that were never built. Four were added to `PipelineController`:

| Endpoint | Shape |
|---|---|
| `GET /projects/{p}/pipelines` | paginated + `filters.refs` for the branch picker |
| `GET /projects/{p}/pipelines/{iid}` | stages, jobs, changes, failures with confidence |
| `GET /projects/{p}/analyses` | rows + `totals` (cost, latency, confidence, cache hit rate) |
| `GET /projects/{p}/signatures` | grouped by signature with an occurrence count |

Bound by **iid**, not uuid, for a pipeline: #821 is the number the provider shows
and the number people quote to each other.

The pipelines list returns `filters.refs` alongside the page. Without it the
branch picker would have to guess the available branches from whatever happened
to land on page one.

`analyses.was_helpful` is deliberately **nullable** rather than defaulting to
false: "nobody has judged this yet" and "somebody judged it wrong" are different
states, and the ML training set depends on telling them apart.

The signature catalogue groups in SQL rather than in the client. Forty failures
of the same error is one row with a count — the shape the information actually
has, and the view that makes recurring problems obvious.

---

## Anomaly detection uses MAD, and the sample floor is load-bearing

`job_baselines` are written only for `(project, job, ref)` with **≥ 10 successful
runs in 30 days**. Below that, spread is meaningless — flagging against three
runs produces confident nonsense, and an alert list nobody trusts is worse than
no alert list.

Duration statistics use **successful runs only**: a job that died after four
seconds would drag the mean down and make every slow-but-passing run look normal.
Failure and retry rates deliberately use all runs, since excluding failures would
make those rates structurally zero.

`MAD = 0` scores **0**, not infinity. A job that has never varied would otherwise
raise a permanent critical alert on its first one-second wobble.

Full method and numbers: [`experiments/anomaly-v1.md`](../../experiments/anomaly-v1.md).

## A hardcoded ratio is not a detector

The memory detector originally used `ratio ≥ 1.5`, because `job_baselines` stored
only `mean_memory_mb` and there was nothing to measure deviation against. On the
first full run it raised **22 anomalies from 24 jobs** — noise with a severity
label, loud enough to bury the one real duration anomaly underneath it.

Migration `2026_01_02_000003` adds `median_memory_mb` and `mad_memory`, and memory
now uses the same modified z-score as duration. 22 findings became 3.

## Auto-resolve must check the metric the anomaly is about

`hasRecovered()` always compared durations, whatever the anomaly measured. Nine
memory anomalies closed themselves because the job's *runtime* had recovered —
live alerts discarded on the evidence of an unrelated measurement. It is now
metric-aware.

Recovery requires **three** consecutive healthy runs. Fewer is absence of
evidence, not evidence of recovery, and closing on it would hide a live problem.

## Severity rises but never silently falls

`AnomalyRecorder` keeps the higher of the stored and incoming severity when
updating an existing row. A critical alert that quietly becomes "low" on the next
marginal recurrence is how a real problem disappears from the top of the list.

Deduplication is per `(project, metric_name, type)` with `detected_at` pinned to
first sighting — the same slow job seen on twenty pipelines is one problem, and
first sighting is when it started.

## "Not an issue" is a first-class action

`PUT /anomalies/{a}/false-positive` records `false_positive` rather than hiding
the row, because that status is what feeds threshold tuning. A detector nobody
can push back on gets ignored within a week, taking the genuine alerts with it.

The false-positive **rate is not yet measurable** — it needs humans pressing the
button, and nobody has used the UI. The status and endpoint exist so the number
becomes available later; quoting one now would be inventing it.

## `helpful_rate` is null, not zero, with no feedback

"0% of analyses were helpful" and "nobody has said whether they were helpful" are
opposite conclusions. The analytics endpoint returns `null` and the UI renders a
dash with "no feedback yet".

## The generated `components.d.ts` can be corrupted by a running dev server

`unplugin-vue-components` rewrites `src/types/components.d.ts` on change. With the
dev server running during a build, the two writers collided and left a truncated
line mid-identifier, which then failed typecheck with errors pointing at the
generated file rather than at any real code.

Recovery is `rm src/types/components.d.ts && npx vite build` — `npm run build`
cannot do it, because it runs `vue-tsc` first and typecheck needs the very file
that is missing.

---

## Static analysis is baselined, not clean

`phpstan.neon` includes `phpstan-baseline.neon` with 431 acknowledged findings —
almost all Eloquent magic properties, which cannot be seen statically without
annotating every column on every model. CI enforces **no new errors**, which is
the gate that actually protects the codebase. A gate that fails on day one is a
gate somebody disables by the end of the week.

It earned its place on the first run by finding a genuine defect (below).

## A public health endpoint that was dead code

`routes/api.php` registered a public health check at `/v1/system/status`, and the
**authenticated** route of the same path silently shadowed it — Laravel keeps the
last registration. Consequences:

- Any uptime monitor pointed at it received **401**.
- The bug inside it, a call to `AiGateway::reachable()` (the method is
  `isReachable()`), was therefore never reached and never complained.

The public check now lives at `/api/health` and returns 200/503 from a real
database probe. It is deliberately minimal: the rich version — model names,
contract version, provider health — stays behind auth, because an
unauthenticated caller has no business learning which model a workspace runs.

**Two routes may never share a path.** Laravel will not warn; the earlier one
simply stops existing.

## `FallbackProvider` was missing `verify()`

`verify()` was added to the `LLMProvider` protocol and implemented on all four
concrete providers — and not on the wrapper. Verifying a fallback-configured
provider raised `AttributeError` at runtime. mypy found it the first time it ran.

The implementation reports on the **primary**, and when only the secondary
answers it says so explicitly. Reporting plain success would tell a user their
Gemini key works when it does not — the fallback exists to keep analyses running,
not to hide a broken credential.

## The `withTeam()` invariant is asserted structurally

A queue worker has no session, so `TeamScope` is inert there — it filters on
`currentTeamId()` and finds nothing bound. A job that queries without
`withTeam()` reads across **every** workspace and writes rows against the wrong
one.

`tests/Feature/Security/JobTenancyTest.php` tokenises each job, strips comments
so a docblock merely *mentioning* `withTeam` cannot pass, and checks for a real
call. It also asserts the premise — that the scope is genuinely inert with no
team bound — because without that the whole invariant would be guarding nothing.

## Three open `transformers` advisories, accepted deliberately

`pip-audit` reports PYSEC-2026-2289, PYSEC-2026-2290 and CVE-2026-9856 against
`transformers 4.57.6`, a transitive dependency of `sentence-transformers`.

The fixes need `transformers >= 5.3.0`, and `sentence-transformers 3.4.1` pins
`transformers < 5.0.0`. The first version that allows 5.x is
**sentence-transformers 6.0.1** — a three-major-version jump of the library that
produces our embeddings.

Not taken as a drive-by upgrade: a new major version may change the vector output
for the same model, which would silently invalidate every row in
`failure_embeddings`. Retrieval would degrade with no error anywhere.

The migration path already exists in the schema: `failure_embeddings.model` with
`UNIQUE (failure_id, model)` allows both models to be stored side by side and
compared before cutover. That is the deliberate task; until then `pip-audit`
runs in CI as **reporting, not gating**. `composer audit` is clean and therefore
does gate.

## Coverage is reported, never guessed

No coverage driver is installed on the development machine (`pcov`/`xdebug`
absent, `pecl` unavailable), so any threshold would be invented. Both CI and
`check-quality.sh` report coverage without enforcing a minimum. Set it from the
number CI prints, once.

## The frontend cannot currently install a dependency

`npm install <anything>` fails with `Cannot read properties of null (reading
'edgesOut')` — an internal arborist error meaning `node_modules` and
`package-lock.json` have diverged. Existing tooling works; only additions fail.

The fix is `rm -rf node_modules package-lock.json && npm install`, which
regenerates a tracked lockfile and may move versions — a deliberate call, not a
side effect of unrelated work. `eslint.config.js` and the `lint` /
`test:coverage` scripts are written and inert until then, and
`check-quality.sh` skips the lint gate with a visible notice rather than
pretending it ran.

## Chunk size is set by the embedder's window, not by taste

`all-MiniLM-L6-v2` reads 256 word-pieces and silently discards the rest. The
chunker targeted 400 "tokens" (a `chars / 4` estimate), which measured 400
word-pieces on a real runbook and 515 on code-heavy text — a third to a half of
every chunk was embedded as if it did not exist, so the fix section of a runbook
could not be retrieved however well it was written.

Chunks are now 150 tokens with 25 of overlap, measured worst-case 146
word-pieces. Below ~120 the chunk loses the context that made it specific and
starts matching unrelated errors; above ~230 the tail is truncated. The invariant
is asserted against the live tokenizer in `test_chunker.py`, not against the
chars-per-token ratio — trusting that ratio is precisely what failed.

The tempting counter-argument, which the old comment in `chunker.py` actually
made, is that chunks should be sized for the LLM's context rather than the
embedder's. It is wrong in one step: text the embedder truncates can never be
retrieved, so it never reaches the LLM either.

Changing `embedding_model` invalidates the chunk size, `similarity_threshold`
and `knowledge_threshold` together — all three are properties of the model.

## Defaults live in one place, and contracts import them

`ChunkEmbedRequest` restated `target_tokens = 400` as a literal, shadowing
`chunker.TARGET_TOKENS`. Retuning the chunker therefore changed nothing for the
only caller that mattered, because every request arrived carrying the stale
default explicitly. Request models now import the constants.

A duplicated default is worse than a magic number: it is a magic number that
looks configured.

## Every similarity cutoff ships with its measurement

Both retrieval thresholds in this system were guesses and both guessed a value
that returned zero rows — `similarity_threshold` at 0.75, `knowledge_threshold`
at 0.60. Neither failed loudly; both reported "nothing found", which is
indistinguishable from "nothing relevant exists".

A threshold without a recorded measurement is a silent feature-off switch. See
`experiments/similarity-threshold.md` and `experiments/knowledge-retrieval.md`.

## Retrieved chunks are expanded to their neighbours

Similarity retrieves the section of a document written in the words of the
error — which, in a runbook, is the symptom. The section holding the fix
describes a remedy and shares almost no vocabulary with the failure: measured on
a real runbook, the symptom chunk scored 0.573 and the chunk containing the
actual fix scored 0.059, near-orthogonal to the query.

No threshold separates that from noise. Matched chunks are therefore treated as
*seeds*, and the chunks around them are fetched too. The neighbours of a hit are
not extra context, they are the answer.

Radius moves with chunk size: at 150 tokens a symptom → cause → fix arc spans
about three chunks, so radius 1 stopped one chunk short of the remedy and radius
2 reaches it. Passages are quoted in document order, never by score — a runbook
read out of sequence looks like contradictory advice and the model cannot tell
which fragment came first.

Measured on one failure with the same model and log, this changed the answer
from "verify database service readiness" to "add a healthcheck and wait for
`condition: service_healthy`", for +301 prompt tokens and +$0.0005.

## A value in two places is duplicated, not configured

Three separate times in one investigation, a deliberately chosen value did
nothing because a stale copy of it won: request-model defaults restating the
chunker's constants, a threshold restated as a literal at its call site, and
`.env` pinning a cap the config had moved past. None of them errored; each just
kept the old behaviour while the code claimed the new one.

Defaults live in exactly one place and are imported. Where an env var may
override one, `.env.example` carries the reason for the value, so whoever edits
the override sees the argument against changing it casually.

## Retrieval needs an end-to-end reachability test

Six bugs sat between a correctly indexed runbook and an answer that used it, and
none raised an error: the document indexed, the query embedded, the search ran,
the prompt rendered, and the feature was dead. Every stage was individually
healthy.

No unit test on any single stage would have caught that. What catches it is an
assertion that a known document is reachable from a known error message, run
against a real index — a retrieval path that can legitimately return empty needs
a test that notices when it *always* does.

## Remediation: Laravel is the execution boundary

The AI service never touches infrastructure. It proposes; `RemediationPolicyEvaluator`
decides; an executor acts. Two rules make that boundary real rather than
stylistic:

**Risk comes from the action type, never from the response.** `ActionType::risk()`
assigns it, so a model that labelled a production rollback "low risk" would gain
nothing — the label is discarded before the gate sees it. Tested directly: a
`rollback_deployment` claiming `risk: low` with confidence 1.0 against a policy
allowing `low` automatically is still refused, and the reason names `critical`.

**A missing policy is FORBIDDEN.** A gap in the table cannot become permission.
That is why `config('pipemind.default_policies')` is seeded at registration —
without it a new workspace could never remediate anything, which is the correct
failure direction but a useless product.

A workspace-level `forbidden` is absolute. A project policy may tighten a limit
or relax a threshold, but it may never re-permit an action the workspace has
banned; otherwise a workspace-wide prohibition is advice.

## The policy is re-evaluated at execution, not trusted from the row

An approval is permission to act *then*. `ExecuteRemediation` re-runs the
evaluator before doing anything, because the policy may have been tightened in
between — and separately, `RemediationPolicyController` cancels approved-but-
unexecuted work when a policy changes to forbid it. Both are needed: without the
re-check a queued approval executes under a policy that no longer exists;
without the cancellation the row keeps claiming "approved" and misreports what is
about to happen.

Three distinct stops, each with its own status, so the trail says which one it
was: `expired` (the approval aged out), `cancelled` (policy changed, or a human
already fixed it), `failed` (the provider refused).

## Patches are applied by parsing, not by shelling out to git

`PatchApplier` reads a unified diff and rewrites the file contents, then commits
through the provider API. The alternative — clone the repository and run
`git apply` — means credentials on disk, a working tree per remediation, and
`git apply`'s own fuzz behaviour. Parsing keeps the whole operation to two API
calls and makes the failure mode inspectable.

It is deliberately stricter than `patch(1)`. Context must match exactly; there is
no fuzz. Fuzzing is the right trade for a human at a terminal who can read the
result and the wrong one for an automated commit nobody has looked at yet, so a
file edited since the analysis produces a clean refusal ("the file has changed")
instead of a silent mangle.

Hunks are located by searching outward from the position the header claims,
because earlier hunks change the file's length and unrelated edits above shift
everything. Matching stays exact once found — the search moves *where* to apply,
never *whether* it matches.

**One bug worth recording.** Every real patch ends with a newline, which
`preg_split` turns into a trailing empty element. Read as a blank context line,
it made the hunk demand a line the file did not have, so nothing applied. Every
heredoc fixture in the unit tests happened to end without a newline — so eleven
passing tests were all exercising an easier case than reality, and the bug only
surfaced when an integration test built its patch with an explicit `\n`.

## A merge request, never a commit to the default branch

`CreateMergeRequestExecutor` is the only code that writes to a repository, and it
enforces three things itself rather than trusting them:

1. The change lands on a new `pipemind/…` branch and is *proposed*. The value of
   a suggested fix is that a person still reads it; committing to `main` would
   make PipeMind the author of unreviewed code.
2. Only files the recommendation declared. A patch touching a path the analysis
   never mentioned is refused — mirroring `validate_patch()` in the AI service.
   This is defence against the model, not against the user.
3. Exact context or nothing, per `PatchApplier` above.

## A validated patch is a merge-request proposal

Every recommendation in the real database arrived as `edit_file` or
`update_config`, and neither has an executor — so the best output of the whole
analysis chain, an applyable diff pinned to the line that broke, could never be
applied. The gap was in the AI service, not the remediation layer.

`sanitize()` now promotes a recommendation to `create_merge_request` when it
carries a patch that survived `validate_patch()`, because branch → commit →
merge request is the only way this system applies a file change.

The promotion keeps the **higher** of the two risks. `update_config` is HIGH and
`create_merge_request` is MEDIUM, so taking the promoted action's own risk would
quietly relax the gate — and the entire reason risk is assigned in code is that
nothing should be able to.

## Outcome watching is what closes the learning loop

"Succeeded" from an executor means the API call was accepted, not that anything
was fixed. `WatchRemediationOutcome` polls for the pipeline the retry produced
and records `outcome_success` — and on green, promotes the signature to `is_known`,
so every future occurrence short-circuits with no model call at all.

`outcome_success` is nullable on purpose: **null is "not verified yet", which is
not "did not fix it"**. Collapsing those would let a slow pipeline look like a
failed remediation.

It never overwrites a resolution a human confirmed, and it records no
`resolution_confirmed_by` for its own inferences — nobody typed them, and
claiming a person vouched would corrupt the provenance that makes the
short-circuit trustworthy.
