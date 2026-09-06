# 05b — Integration Layer

**Repo:** `PipeMind-back` + `PipeMind-front` · **Depends on:** 05, 14 · **Milestone:** M2

The wizard that connects a CI/CD platform, proves the credentials work, imports repositories and registers webhooks — plus the re-register button that makes a rotating dev tunnel survivable.

> Slots between files 05 and 06. It also covers onboarding steps 2–3 from file 13, so that file gets shorter.

---

## Design decisions

**Test before saving.** The wizard proves credentials work at step 3 before it is willing to persist a token. That needs two endpoints — `POST /integrations/test` operates on unsaved credentials; `POST /integrations/{i}/test` retests a stored one.

**Report capability, don't claim it.** `verify()` returns a `ProviderIdentity` carrying `canReadProjects`, `canRetryJobs`, `canWriteIssues`, probed rather than assumed. Half of all integration support burden is a token with the wrong scope; showing "retry jobs: no" at setup turns a confusing failure three days later into a clear choice now.

**Per-repository import status.** Import returns `207 Multi-Status` when any webhook fails. A project imported without a working hook looks fine and does nothing — the worst possible failure mode, so it is reported per repository rather than as one boolean.

**The webhook base URL is a team setting, not `APP_URL`.** A free cloudflared or ngrok tunnel gets a **new hostname on every restart**. Storing it in `teams.settings` means the user pastes the current URL into the UI and re-registers, instead of editing `.env` and redeploying.

**Re-registration is a first-class operation.** Not an edge case. It also removes the previous hook so a rotating tunnel does not leave a trail of dead webhooks on the provider side.

**Reachability is checked and stated.** A `localhost` webhook URL means providers cannot reach PipeMind at all. Saying so up front beats letting registration succeed and then wondering why no pipelines arrive.

---

## Backend

```text
app/Services/Integrations/
├── ConnectionTester.php    verify unsaved or stored credentials
├── WebhookRegistrar.php    register / re-register / unregister
└── ProjectImporter.php     create projects + hooks, per-repo status
```

| Method | Path | Notes |
|---|---|---|
| POST | `/integrations/test` | **Unsaved** credentials. Persists nothing |
| GET | `/integrations/webhook-settings` | Base URL + `reachable` flag |
| GET/POST | `/integrations` | list · create (re-verifies before saving) |
| GET/PUT/DELETE | `/integrations/{i}` | delete also removes provider-side hooks |
| POST | `/integrations/{i}/test` | retest, records status + `last_error` |
| GET | `/integrations/{i}/remote-projects` | searchable, flags `already_imported` |
| POST | `/integrations/{i}/import` | 201, or **207** if any webhook failed |
| POST | `/integrations/{i}/re-register` | optional `webhook_base_url` to update first |

All behind `can.do:integrations.manage` (owner/admin).

```php
// ready — Team: the rotating-tunnel escape hatch
public function webhookBaseUrl(): string
{
    return rtrim($this->settings['webhook_base_url'] ?? config('app.url'), '/');
}

public function webhookUrlIsReachable(): bool
{
    $host = parse_url($this->webhookBaseUrl(), PHP_URL_HOST) ?: '';

    return ! in_array($host, ['localhost', '127.0.0.1', '::1'], true)
        && ! str_ends_with($host, '.local')
        && ! str_ends_with($host, '.test');
}
```

---

## Frontend

```text
src/components/integrations/
├── providerCatalog.ts     per-platform spec: auth fields, scope hints, token URL
├── ProviderPicker.vue
├── ConnectionResult.vue   the capability table
├── IntegrationWizard.vue  4 steps + result
├── IntegrationCard.vue    status, last event, actions
└── WebhookUrlPanel.vue    paste tunnel URL → re-register everything
```

`providerCatalog.ts` is where each platform's differences live: whether a cloud option exists, which auth fields it needs, the exact scope requirement, and a deep link to create a token. Adding a provider is one entry.

**Scope hints matter.** GitHub: *"Needs `repo` and `workflow`. A token without `repo` can monitor pipelines but cannot retry jobs or open issues."* That sentence prevents a whole category of support question.

---

## Tunnel workflow

```bash
cloudflared tunnel --url http://localhost:8000
# → https://random-words-1234.trycloudflare.com
```

Paste it into **Integrations → Public webhook URL → Save & re-register all webhooks**. Every hook is re-pointed in one action.

A named cloudflared tunnel gives a permanent hostname and removes the need entirely — worth setting up if you have a domain on Cloudflare.

---

## Tasks

- [ ] Three services + controller + routes
- [ ] `integrations.manage` in the role matrix
- [ ] Types, query hooks, six components, `IntegrationsView`
- [ ] Sidebar entry wired to the real route
- [ ] Tests: capability reporting, refusing bad credentials, secret non-exposure, `already_imported`, partial import (207), re-register, reachability warning, role denial

## Definition of Done

```bash
php artisan test --filter=Integrations      # 9 passed
```

- [ ] Testing credentials persists nothing
- [ ] Bad credentials are never saved
- [ ] Token and webhook secret never appear in any response
- [ ] A failing webhook returns 207 and names the repository
- [ ] Re-register updates the base URL and re-points every hook
- [ ] A `localhost` base URL shows the reachability warning
- [ ] A member (non-admin) gets 403 on every route

---

## Gotchas found while building this

**A cached `bootstrap/cache/config.php` overrides every `<env>` in `phpunit.xml`.** A stale one sent queued jobs to Redis instead of running them inline, and eleven ingestion tests failed in ways that looked like application bugs. `tests/Feature/EnvironmentTest.php` now asserts no cached config exists, that the queue is `sync`, and that the test database is `pipemind_test`.

**Fixtures with hardcoded dates rot.** A `finished_at` of "2026-08-30" stops satisfying `whereDate('failed_at', today())` a day later. Anchor fixture timestamps to `now()` in the test helper.

**`Http::fake()` matches the full URL including the query string.** `'*/diff'` does not match `.../diff?per_page=100`. Trailing `*` on every pattern.
