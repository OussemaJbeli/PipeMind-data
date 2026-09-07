# Log processing — benchmark v1

**Run:** 2026-09-06 · `scripts/benchmark_processing.py` · reproduce with
`cd PipeMind-ai && ./.venv/bin/python scripts/benchmark_processing.py`

Two numbers matter here and they are not equally important. **Reduction** is the
easy metric — how much smaller the excerpt is. **Root-cause retention** is the one
that decides correctness. An excerpt 99.9% smaller that drops the actual error has
made the system worse, not cheaper, so retention is a hard gate and reduction is a
nice-to-have.

## Reduction and retention

| Log | In | Out | Reduction | Root cause kept | Ecosystem | Time |
|---|---|---|---|---|---|---|
| `failed-db-test.log` | 44 ln | 31 ln | 31.6% | yes | db | 1.0 ms |
| `failed-npm-dependency.log` | 18 ln | 17 ln | 0.2% | yes | node | 0.4 ms |
| synthetic 1k | 1 202 ln | 31 ln | 99.0% | yes | db | 9.5 ms |
| synthetic 10k | 10 202 ln | 31 ln | 99.9% | yes | db | 87.3 ms |
| synthetic 50k | 50 202 ln | 31 ln | 100.0% | yes | db | 499.4 ms |

**Root-cause retention: 5/5.**

Output size is flat at 31 lines regardless of input — the excerpt window is fixed,
so cost per analysis does not grow with log size. A 50 000-line log costs the same
in tokens as a 1 200-line one.

Processing is linear and cheap: ~10 µs per line. Half a second for a 50 000-line
log is well inside the ingestion job's budget, and it happens once per failure.

Reduction on the two real fixtures is low (31.6% and 0.2%) only because they are
already short. Reduction is a function of input noise, not of extraction quality —
which is exactly why retention is the gate.

## Signature stability

The metric deduplication actually depends on. If a run-scoped value reaches the
hash, the same recurring failure gets a fresh signature every time, and
`occurrence_count`, the analysis cache and the known-signature short-circuit all
stop working — silently, with no error anywhere.

| Noise lines around the same error | Hash |
|---|---|
| 0 | `21897bd82a8b3e8c…` |
| 50 | `21897bd82a8b3e8c…` |
| 1 000 | `21897bd82a8b3e8c…` |
| 10 000 | `21897bd82a8b3e8c…` |
| 50 000 | `21897bd82a8b3e8c…` |

Stable across a 50 000× change in surrounding noise.

## Separation

Five genuinely different failures, five distinct signatures — including the pair
that matters most, `SQLSTATE[2002]` (cannot connect) against `SQLSTATE[1045]`
(access denied). Those share almost all their text and have completely different
fixes; collapsing them would mean one cache entry and one wrong answer for two
unrelated problems.

```
21897bd82a8b3e8c…   SQLSTATE[HY000] [2002] Connection refused
ff8336afaab748f5…   Error: connect ECONNREFUSED 127.0.0.1:5432
17704cf04f6af282…   npm ERR! ERESOLVE unable to resolve dependency tree
9e6442edf7507ea6…   FATAL ERROR: Reached heap limit Allocation failed
1bb36b261a7f7924…   SQLSTATE[HY000] [1045] Access denied for user

unique: 5/5
```

## A bug this benchmark found

The signature arm did not exist when the script was first written — it measured
reduction only. Adding it immediately exposed a real defect.

Three runs of the same failure, differing only in timestamp and process id,
produced **three different hashes**:

```
sqlstate[hy000] [2002] connection refused at <timestamp> pid=<num>
sqlstate[hy000] [2002] connection refused at <timestamp> pid=99
sqlstate[hy000] [2002] connection refused at <timestamp> pid=7
```

The generic `<num>` normaliser matches `\b\d{3,}\b` — three or more digits. That
floor is deliberate: it protects `:42` line numbers and small diagnostic codes
from being erased. But it let short volatile values straight through, so
`pid=4821` normalised while `pid=99` and `pid=7` did not.

In practice that meant most repeat failures would have been recorded as brand new
ones. Nothing would have errored. `occurrence_count` would simply have stayed at 1
forever, the cache would never have hit, and "seen 12 times before" would never
have appeared.

Fixed with a targeted rule for run-scoped identifiers (`pid`, `ppid`, `tid`,
`thread`, `worker`, `job`, `build`, `run`, `attempt`, `retry`, `try`, `seq`) at any
digit count, placed **before** the generic rule so the 3-digit floor stays intact
for everything else. Locked in by `TestVolatileIdentifiers` and
`TestMeaningfulNumbersSurvive` in `tests/unit/test_signature.py` — the second class
guards the opposite failure, since over-normalising is just as damaging.

**Lesson worth keeping:** the benchmark measured the metric that was easy to
measure. The defect was in the one that was not being measured at all.

## Limits

- The three synthetic logs share one error and one noise shape. Real logs vary far
  more, and reduction figures will move.
- Only two real fixtures, both short. Numbers should be re-run once genuine
  multi-thousand-line CI logs land from the lab repository.
- Retention is checked by substring match against a known phrase, which proves the
  line survived — not that the excerpt is the *most useful* window around it.
