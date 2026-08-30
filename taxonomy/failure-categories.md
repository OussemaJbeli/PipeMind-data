# Failure Taxonomy v1

The 13 categories PipeMind classifies into. Used by the rule engine (roadmaps/08),
the ML classifier, the LLM prompt, and every chart in the UI.

**These labels are a contract.** Changing one means retraining the classifier,
relabelling the dataset, and updating `App\Enums\FailureCategory`, the frontend
`CATEGORY_META`, and the colours below — which must match across all three.

---

## Labelling rules

Apply in order. These exist because the same log can plausibly take several labels,
and an inconsistent dataset is worse than a small one.

1. **Label the root cause, not the symptom.** A test that fails because the database
   is unreachable is `DATABASE`, not `TEST`.
2. **When two apply, pick the one whose fix is correct.** A dependency conflict that
   surfaces as a compile error is `DEPENDENCY` — you edit `package.json`, not the compiler.
3. **`UNKNOWN` is a real label.** Forcing a guess pollutes every other class. Anything
   below the confidence floor stays `UNKNOWN`.
4. **`RESOURCE` outranks everything.** If OOM or disk-full is present it explains the
   rest of the log, whatever else appears.
5. **`TEST` is the last resort**, not the first. A failing assertion is only a `TEST`
   failure when the test itself is genuinely wrong.

---

## Categories

### RESOURCE
Checked first — it explains other symptoms.

| Subcategory | Signature examples |
|---|---|
| OutOfMemory | `OOMKilled` · `JavaScript heap out of memory` · `exit code 137` · `java.lang.OutOfMemoryError` |
| DiskFull | `no space left on device` · `ENOSPC` · `disk quota exceeded` |
| CPUThrottle | `context deadline exceeded` under sustained load |
| FileDescriptors | `EMFILE: too many open files` |

```
/usr/bin/node: line 1: 4821 Killed  node --max-old-space-size=2048 build.js
FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory
ERROR: Job failed: exit code 137
```

---

### DATABASE

| Subcategory | Signature examples |
|---|---|
| ConnectionRefused | `SQLSTATE[HY000] [2002]` · `could not connect to server` · `ECONNREFUSED …:5432` |
| AuthFailed | `password authentication failed` · `Access denied for user` · `SQLSTATE[28000]` |
| MigrationError | `relation "users" already exists` · `SQLSTATE[42S02]` · `Base table or view not found` |
| SchemaMismatch | `column "x" does not exist` |
| Timeout | `statement timeout` · `Lock wait timeout exceeded` |
| Deadlock | `deadlock detected` |

```
SQLSTATE[HY000] [2002] Connection refused
  at vendor/laravel/framework/src/Illuminate/Database/Connectors/Connector.php:70
Illuminate\Database\QueryException: could not find driver (SQL: select 1)
```

---

### DEPENDENCY

| Subcategory | Signature examples |
|---|---|
| Conflict | `ERESOLVE unable to resolve dependency tree` · `Your requirements could not be resolved` |
| NotFound | `Cannot find module` · `Could not find a version that satisfies` · `404 Not Found - GET https://registry.npmjs.org/…` |
| VersionMismatch | `peer vue@"^2.0.0" from package-x` |
| LockfileDrift | `npm ci can only install with an existing package-lock.json` · `composer.lock is not up to date` |
| RegistryError | `npm ERR! ETIMEDOUT` against a registry host |
| AuditFail | `found 3 high severity vulnerabilities` in a gating job |

```
npm ERR! ERESOLVE unable to resolve dependency tree
npm ERR! While resolving: frontend@1.0.0
npm ERR! Found: vue@3.5.0
npm ERR! Could not resolve dependency:
npm ERR! peer vue@"^2.0.0" from package-x@1.4.2
```

---

### DOCKER

| Subcategory | Signature examples |
|---|---|
| RegistryAuth | `pull access denied` · `unauthorized: authentication required` · `denied: requested access to the resource is denied` |
| ImageNotFound | `manifest unknown` · `manifest for … not found` |
| BuildFailed | `failed to solve` · `The command '/bin/sh -c …' returned a non-zero code: 1` |
| DaemonUnavailable | `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` |
| LayerError | `failed to register layer` |

```
#12 [builder 6/9] RUN npm ci --omit=dev
#12 ERROR: process "/bin/sh -c npm ci --omit=dev" did not complete successfully: exit code: 1
------
failed to solve: process "/bin/sh -c npm ci --omit=dev" did not complete successfully
```

---

### NETWORK

| Subcategory | Signature examples |
|---|---|
| DNSFailure | `getaddrinfo ENOTFOUND` · `Temporary failure in name resolution` · `Could not resolve host` |
| Timeout | `ETIMEDOUT` · `Connection timed out` · `context deadline exceeded` |
| ConnectionReset | `ECONNRESET` · `Connection reset by peer` · `broken pipe` |
| ProxyError | `502 Bad Gateway` from a proxy hop |
| TLSError | `certificate has expired` · `x509: certificate signed by unknown authority` · `unable to get local issuer certificate` |

```
curl: (6) Could not resolve host: api.internal.example
npm ERR! network request to https://registry.npmjs.org/vue failed, reason: getaddrinfo EAI_AGAIN
```

---

### TEST

| Subcategory | Signature examples |
|---|---|
| UnitTest | `Tests: 1 failed, 42 passed` · `FAILURES!` |
| IntegrationTest | failure in a job named `integration`/`api-test` |
| E2ETest | `Timed out retrying after 4000ms` (Cypress/Playwright) |
| Assertion | `AssertionError` · `Failed asserting that 401 matches expected 200` |
| Snapshot | `snapshot does not match` |
| Coverage | `Coverage for lines (68%) does not meet threshold (80%)` |

```
FAIL src/auth/login.test.ts
  ✕ returns a token for valid credentials (34 ms)
    expect(received).toBe(expected)
    Expected: 200
    Received: 401
Tests: 1 failed, 12 passed, 13 total
```

---

### BUILD

| Subcategory | Signature examples |
|---|---|
| Compilation | `syntax error` · `PHP Parse error` · `cannot find symbol` |
| TypeCheck | `error TS2345: Argument of type 'string' is not assignable` · `mypy: error` |
| Bundling | `Module build failed` · `Rollup failed to resolve import` |
| Linting | `✖ 14 problems (14 errors, 0 warnings)` · `PHP_CodeSniffer … ERRORS` |
| AssetGeneration | `Failed to compile SCSS` |

```
src/services/auth.ts:42:18 - error TS2345: Argument of type 'string | undefined'
is not assignable to parameter of type 'string'.
Found 1 error in src/services/auth.ts:42
```

---

### CONFIGURATION

| Subcategory | Signature examples |
|---|---|
| MissingEnvVar | `variable APP_KEY not set` · `$DATABASE_URL: unbound variable` |
| InvalidYAML | `yaml: line 12: mapping values are not allowed in this context` · `Invalid CI config` |
| WrongPath | `No such file or directory` · `ENOENT: no such file or directory, open '.env'` |
| MissingSecret | `secret 'deploy-key' not found` |
| InvalidValue | `Invalid value for option --workers` |

```
ERROR: .gitlab-ci.yml: jobs:test:script config should be a string or an array
```

---

### AUTHENTICATION

| Subcategory | Signature examples |
|---|---|
| InvalidToken | `401 Unauthorized` · `Bad credentials` · `invalid_token` |
| ExpiredToken | `token has expired` · `JWT expired` · `credentials have expired` |
| MissingToken | `Authorization header missing` |
| Unauthorized | `HTTP 401` from an API the pipeline calls |
| MFARequired | `two-factor authentication required` |

---

### PERMISSION

| Subcategory | Signature examples |
|---|---|
| FilePermission | `EACCES: permission denied, open '/app/storage/logs'` · `Operation not permitted` |
| RegistryPermission | `403 Forbidden` pushing an image |
| RepoPermission | `You are not allowed to push code to this project` |
| SudoRequired | `must be run as root` |

> `403` is `PERMISSION` (identity known, access refused). `401` is `AUTHENTICATION`
> (identity not established). This distinction drives different fixes and must stay consistent.

---

### DEPLOYMENT

| Subcategory | Signature examples |
|---|---|
| HealthCheckFailed | `readiness probe failed` · `CrashLoopBackOff` · `health check failed` |
| RolloutTimeout | `deployment "api" exceeded its progress deadline` · `rollout timed out` |
| RollbackTriggered | `rolling back to revision 4` |
| EnvMismatch | config present in staging, absent in production |

---

### INFRASTRUCTURE

| Subcategory | Signature examples |
|---|---|
| RunnerUnavailable | `This job is stuck because no runners are online` · `no runner matched` |
| NodeFailure | `job was cancelled by the system` · `runner system failure` |
| QuotaExceeded | `429 Too Many Requests` · `API rate limit exceeded` · `quota exceeded` |
| ServiceDown | a required external service returns 5xx |

---

### UNKNOWN

No rule matched and the classifier was below the confidence floor. Not a failure of
the system — a legitimate, honest label. Track its share over time: a rising
`UNKNOWN` rate means the taxonomy needs a new category or the rules need extending.

---

## Colours

Must match `App\Enums\FailureCategory::color()` (backend) and `CATEGORY_META`
(frontend) exactly. Divergence makes the donut and the bar list disagree.

| Category | Hex |
|---|---|
| DATABASE | `#A9E831` |
| TEST | `#F04438` |
| DEPENDENCY | `#F5A524` |
| DOCKER | `#38BDF8` |
| NETWORK | `#6366F1` |
| BUILD | `#EC4899` |
| DEPLOYMENT | `#14B8A6` |
| CONFIGURATION | `#A855F7` |
| AUTHENTICATION | `#F97316` |
| PERMISSION | `#8B5CF6` |
| INFRASTRUCTURE | `#0EA5E9` |
| RESOURCE | `#EAB308` |
| UNKNOWN | `#5C6472` |

---

## Version history

| Version | Date | Change |
|---|---|---|
| v1 | 2026-08-30 | Initial taxonomy: 13 categories, 47 subcategories |

Real data should drive revisions. If the confusion matrix (roadmaps/08) shows two
categories persistently collapsing into each other, that is evidence they should merge —
not evidence the model needs more training.
