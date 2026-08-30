# 21 — Testing & Quality

**Repo:** all · **Depends on:** 20 · **Milestone:** ship

The test suite that lets you change things without fear, plus the static analysis and CI gates.

---

## 21.1 What to test, and what not to

Do not chase a coverage number. Chase the failures that would actually hurt.

| Priority | Area | Why |
|---|---|---|
| **Critical** | Tenancy isolation | A cross-team leak ends the project |
| **Critical** | Secret redaction | Shipping credentials to a third party |
| **Critical** | Policy engine | An unauthorised action on infrastructure |
| **Critical** | Webhook signature verification | Forged pipeline data |
| **High** | Ingestion idempotency | Duplicate/lost pipelines corrupt every metric |
| **High** | Status normalization | Wrong status = every chart lies |
| **High** | Signature stability | Breaks dedupe, cache and similarity at once |
| **Medium** | API response shapes | Frontend breakage |
| **Medium** | Classification accuracy | Measured in file 08, not unit-tested |
| **Low** | UI component rendering | Cheap to fix, visible immediately |

---

## 21.2 Backend — Pest

```php
// ready — tests/Feature/Security/TenancyTest.php
// One test per list endpoint. This is the suite that must never be skipped.
dataset('tenant_endpoints', [
    'workspace projects' => ['/api/v1/workspace/projects'],
    'workspace activity' => ['/api/v1/workspace/activity'],
    'projects'           => ['/api/v1/projects'],
    'failures'           => ['/api/v1/failures'],
    'remediations'       => ['/api/v1/remediations'],
    'integrations'       => ['/api/v1/integrations'],
    'ai providers'       => ['/api/v1/ai-providers'],
    'signatures'         => ['/api/v1/signatures'],
]);

it('never returns another team\'s data', function (string $endpoint) {
    $mine   = User::factory()->withTeam()->create();
    $theirs = User::factory()->withTeam()->create();

    seedFullWorkspace($theirs->currentTeam);      // projects, pipelines, failures, everything

    $response = $this->actingAs($mine)->getJson($endpoint)->assertOk();

    expect($response->json('data'))->toBeEmpty();
})->with('tenant_endpoints');

it('rejects a direct uuid lookup across teams', function () {
    $mine   = User::factory()->withTeam()->create();
    $theirs = User::factory()->withTeam()->create();
    $failure = Failure::factory()->for($theirs->currentTeam)->create();

    $this->actingAs($mine)
        ->getJson("/api/v1/failures/{$failure->uuid}")
        ->assertNotFound();       // 404, not 403 — don't confirm it exists
});
```

```php
// ready — tests/Feature/Security/SecretLeakTest.php
it('never returns integration credentials through any endpoint', function () {
    $user = User::factory()->withTeam()->create();
    Integration::factory()->for($user->currentTeam)->create([
        'credentials' => ['token' => 'glpat-SUPERSECRET1234567890'],
    ]);

    foreach (['/api/v1/integrations', '/api/v1/workspace/projects', '/api/v1/projects'] as $endpoint) {
        $body = $this->actingAs($user)->getJson($endpoint)->content();
        expect($body)->not->toContain('SUPERSECRET')
            ->and($body)->not->toContain('webhook_secret');
    }
});
```

```php
// ready — a queued-job invariant every job must satisfy
it('binds a team in every queued job', function () {
    $jobs = collect(File::allFiles(app_path('Jobs')))
        ->map(fn ($f) => File::get($f->getPathname()));

    foreach ($jobs as $source) {
        // Jobs run without an authenticated user; without withTeam() the global
        // scope is inert and the job silently operates across all tenants.
        expect($source)->toContain('withTeam(');
    }
});
```

**Coverage targets** — meaningful, not maximal:

| Area | Target |
|---|---|
| `app/Services` | 85% |
| `app/Jobs` | 80% |
| `app/Integrations` | 90% |
| `app/Policies` | 100% |
| `app/Http/Controllers` | 70% |
| Overall | 75% |

---

## 21.3 AI service — pytest

```python
# ready — tests/unit/test_redaction_matrix.py
import pytest
from app.services.redactor import redact

LEAKS = [
    ("AWS", "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("GitHub", "token: ghp_" + "a" * 36, "ghp_"),
    ("GitLab", "glpat-abcdefghij1234567890", "glpat-"),
    ("JWT", "Bearer eyJhbGciOi.eyJzdWIiOiI.SflKxwRJSM", "eyJhbGciOi"),
    ("DB URL", "postgres://user:hunter2@db:5432/app", "hunter2"),
    ("env", "DATABASE_PASSWORD=s3cr3t-value", "s3cr3t-value"),
    ("private key", "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", "MIIE"),
]

@pytest.mark.parametrize("name,text,secret", LEAKS, ids=[l[0] for l in LEAKS])
def test_secret_is_removed(name, text, secret):
    assert secret not in redact(text).text


KEEPS = [
    ("commit sha", "HEAD is now at a82c91f3b4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9"),
    ("image digest", "sha256:" + "a" * 64),
    ("version", "installed vue@3.5.13"),
    ("path", "at /srv/app/Services/PaymentService.php:42"),
]

@pytest.mark.parametrize("name,text", KEEPS, ids=[k[0] for k in KEEPS])
def test_signal_survives(name, text):
    # Over-redaction destroys the diagnosis. These must pass through untouched.
    out = redact(text).text
    assert "[REDACTED" not in out
```

```python
# ready — tests/integration/test_analyze.py
@pytest.mark.parametrize("fixture,expected_category", [
    ("failed-db-test.log", "DATABASE"),
    ("failed-npm-dependency.log", "DEPENDENCY"),
    ("failed-docker-space.log", "RESOURCE"),
    ("failed-phpunit.log", "TEST"),
    ("failed-timeout.log", "NETWORK"),
])
async def test_analysis_identifies_category(client, fixture, expected_category, fake_llm):
    """Golden-file test: real logs in, expected category out."""
    ...
```

- [ ] Redaction matrix: every rule + every negative
- [ ] Golden-file analysis tests for all five fixtures
- [ ] Provider tests with `respx`: success, 429, timeout, malformed JSON
- [ ] Contract tests: request/response schemas validate

---

## 21.4 Frontend — Vitest + Playwright

```ts
// ready — tests/unit/format.spec.ts
describe('deltaTone', () => {
  it('treats a decrease as positive when down is good', () => {
    // Fewer failures is an improvement. Getting this wrong paints every
    // improvement red across the entire dashboard.
    expect(deltaTone(-25, 'down')).toBe('positive')
    expect(deltaTone(25, 'down')).toBe('negative')
    expect(deltaTone(25, 'up')).toBe('positive')
  })
})
```

```ts
// ready — tests/e2e/failure-investigation.spec.ts
test('a developer can go from dashboard to root cause', async ({ page }) => {
  await login(page)

  await page.goto('/app')
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening)/ })).toBeVisible()

  await page.getByRole('button', { name: 'Open Project' }).first().click()
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

  await page.getByText('#821').click()

  // The trust-model assertion: facts and inference must be separately labelled.
  await expect(page.getByRole('heading', { name: 'Observed' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'PipeMind Analysis' })).toBeVisible()

  await expect(page.getByText(/High confidence · \d+%/)).toBeVisible()
  await expect(page.getByText('SQLSTATE[HY000]')).toBeVisible()
  await expect(page.getByText('docker-compose.yml')).toBeVisible()
})

test('an AI outage does not look like a pipeline problem', async ({ page }) => {
  await mockApi(page, '/failures/*', { status: 'analysis_failed' })
  await page.goto('/app/projects/biker-api/failures/xxx')

  await expect(page.getByText('Analysis could not be completed')).toBeVisible()
  await expect(page.getByText('The pipeline failure is real')).toBeVisible()
})
```

- [ ] Unit tests for utils, composables, stores
- [ ] Component tests for `KpiTile`, `ProjectCard`, `AnalysisPanel`, `LogViewer`
- [ ] Four E2E journeys: onboarding, investigation, remediation approval, team switching
- [ ] Visual regression on the two target pages (Playwright screenshots vs `ui/*.png` layout)

---

## 21.5 Static analysis & CI gates

```yaml
# ready — quality gates that must pass before merge
backend:  pint --test · phpstan level 6 · pest --coverage --min=75
ai:       ruff check · ruff format --check · mypy app · pytest --cov --cov-fail-under=70
frontend: eslint · vue-tsc --noEmit · vitest run --coverage · playwright test
security: gitleaks detect · composer audit · npm audit --audit-level=high · pip-audit
```

**`gitleaks` runs on every commit, in a pre-commit hook and in CI.** This project handles credentials by design; a leaked test token in git history is a plausible and embarrassing failure mode.

- [ ] All gates configured and green
- [ ] Pre-commit hooks (`lint-staged` + `gitleaks`)

---

## Definition of Done

```bash
cd PipeMind-back  && composer lint && composer analyse && php artisan test --coverage
cd PipeMind-ai    && ruff check . && mypy app && pytest --cov
cd PipeMind-front && npm run lint && npx vue-tsc --noEmit && npm run test && npx playwright test
gitleaks detect --source . --no-git
```

- [ ] Everything green
- [ ] Tenancy suite passes for all eight endpoints
- [ ] Redaction matrix passes with zero over-redaction
- [ ] `withTeam()` invariant holds for every job

**Next:** [`22-deployment-cicd.md`](22-deployment-cicd.md)
