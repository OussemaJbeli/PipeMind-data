# GitHub Actions failure lab

Produces real CI failures on demand, for three purposes:

1. **Training data** — real logs from a real runner using real tooling. A
   hand-written log teaches a classifier what a person *thinks* npm output looks
   like, which is not the same thing.
2. **Testing the GitHub log path** — Actions returns logs as a ZIP of per-step
   files behind a short-lived signed redirect. That code path only ever runs
   against real GitHub.
3. **A demo you can trigger on cue.**

## Setup

```bash
mkdir -p .github/workflows
cp pipemind-lab.yml .github/workflows/
git add .github/workflows/pipemind-lab.yml
git commit -m "add PipeMind failure lab"
git push
```

Then: **Actions → PipeMind Lab → Run workflow →** pick a mode.

## Modes and what each exercises

| Mode | Real error produced | Expected category |
|---|---|---|
| `none` | — | pipeline succeeds |
| `dependency-conflict` | npm `ERESOLVE` — vue-router@4 against Vue 2 | DEPENDENCY / Conflict |
| `dependency-missing` | npm `404 Not Found` | DEPENDENCY / NotFound |
| `database-refused` | libpq connection refused on the wrong port | DATABASE / ConnectionRefused |
| `database-auth` | `password authentication failed` | DATABASE / AuthFailed |
| `test-assertion` | node:test `Expected status 200, Received 401` | TEST / Assertion |
| `typecheck` | `error TS2345` on `string \| undefined` | BUILD / TypeCheck |
| `network-dns` | curl `Could not resolve host` | NETWORK / DNSFailure |
| `out-of-memory` | V8 `heap out of memory` | RESOURCE / OutOfMemory |
| `env-missing` | required variable not set | CONFIGURATION / MissingEnvVar |
| `permission-denied` | `Permission denied` on an unreadable file | PERMISSION / FilePermission |
| `docker-build` | `docker build` step returns non-zero | DOCKER / BuildFailed |
| `flaky` | passes or fails on the *same commit* | detected as `is_flaky` |

## Suggested first run

Do these three, in order:

1. `none` — proves ingestion works on a green pipeline
2. `database-refused` — the failure the whole product was designed around
3. `dependency-conflict` — a completely different ecosystem and category

Three runs give three real logs across three categories. `flaky` is worth running
twice on the same commit, because that is precisely what flaky detection looks
for and it cannot be faked with a single run.

## Verified locally

Each mode was executed on this machine before shipping, to confirm it produces
the error the taxonomy expects rather than a shell error:

```
test-assertion   not ok 2 - login returns a token for valid credentials
                     Expected status 200, Received status 401
typecheck        src/auth.ts(2,15): error TS2345: Argument of type
                 'string | undefined' is not assignable to parameter of type 'string'
network-dns      curl: (6) Could not resolve host: ...
permission       cat: locked: Permission denied
```

`out-of-memory` is deliberately **not** run locally — V8 exhausting the heap
takes the whole process group with it. On a GitHub runner it is contained.

## Note on the `test` job

Its Postgres service deliberately has **no health check**. `database-refused`
depends on connecting before Postgres finishes starting — which is the single
most common real-world CI database failure, and the one in the mockups.
