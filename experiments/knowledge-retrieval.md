# Knowledge retrieval: why the feature returned nothing

**Date:** 2026-09-07
**Status:** resolved, calibrated on a small corpus, provisional until real runbooks exist
**Related:** [similarity-threshold.md](similarity-threshold.md) — the same class of mistake, one layer down

## Symptom

The Knowledge CRUD went in, a runbook indexed cleanly (3 chunks, 970 tokens,
`indexed_at` set), and retrieval returned **zero chunks** for the exact error the
runbook was written about. Nothing logged a failure: `rag.retrieved` reported
`chunks=0` and the analysis proceeded without documentation, which is
indistinguishable from "no relevant document exists".

That silence is the actual defect. The third RAG source was dead and the only
symptom was slightly worse answers.

## Four independent bugs, each sufficient on its own

### 1. `project_id=None`, hardcoded

`analyzer.py` passed `project_id=None` into `retrieve()` unconditionally, and
`find_knowledge_chunks` filters:

```sql
AND (kd.project_id IS NULL OR kd.project_id = CAST(:project_id AS bigint))
```

So only team-wide documents could ever match. Every project-scoped runbook — the
common case, and the only case the UI creates by default — was unreachable.

The cause was upstream: `AnalyzeRequest.project` carried `uuid` but no numeric
id, while `knowledge_documents.project_id` is a bigint. `None` was written
because there was nothing else to write.

**Fix:** `ProjectContext.id` added to the contract (optional, so old payloads
degrade to team-wide instead of erroring); Laravel's `AnalysisContextBuilder`
sends `$project->id`.

### 2. Threshold 0.60, never measured

Measured on a 6-probe / 9-document corpus (6 matching runbooks, 3 distractors),
48 non-matching pairs:

| threshold | recall | false hits | precision |
|-----------|--------|-----------|-----------|
| 0.60      | 4/6    | 0         | 1.00      |
| 0.50      | 5/6    | 0         | 1.00      |
| **0.40**  | **6/6**| **1**     | **0.86**  |
| 0.30      | 6/6    | 4         | 0.60      |

0.60 hid a third of genuine matches. 0.40 recovers all of them for one weak extra
chunk in 48. Retrieval feeds a ranked, capped list into a prompt, so a marginal
extra chunk costs a few hundred tokens while a missed runbook costs the whole
feature — the asymmetry says favour recall.

**Fix:** `knowledge_threshold = 0.40` in config; the hardcoded `0.60` at the call
site removed.

### 3. Chunks larger than the embedder can read

The real reason the flagship case failed. The chunker targeted **400 tokens**;
`all-MiniLM-L6-v2` truncates at **256 word-pieces**. A runbook chunk measured 400
word-pieces — **36% silently dropped**. The model stopped reading mid-`healthcheck`,
so the entire fix section and the Redis note were unretrievable.

Sweeping target size against the same document:

| target | chunks | max word-pieces | truncated | score for the exact error it documents |
|--------|--------|-----------------|-----------|------------------|
| 400    | 2      | 400             | 1         | 0.334 — below any usable threshold |
| 300    | 2      | 321             | 1         | 0.334 |
| 220    | 3      | 219             | 0         | 0.349 |
| 180    | 3      | 191             | 0         | 0.365 |
| **150**| **5**  | **146**         | **0**     | **0.573** |
| 120    | 5      | 137             | 0         | 0.573 (distractor rises to 0.242) |
| 90     | 7      | 97              | 0         | 0.573 (distractor rises to 0.362) |

Two failure modes bracket the choice: above ~230 tokens the tail is truncated;
below ~120 chunks lose the context that made them specific and drift toward
matching anything. 150 maximises the margin — worst true match 0.551 against
worst distractor 0.185.

Note the estimate itself is the trap. The chunker counts "tokens" as
`chars / 4`; on code-heavy text (yaml, identifiers, punctuation) the real ratio
is nearer 3.6, and the test fixture built from a compose snippet produced **515**
word-pieces at `target_tokens=400` — double the limit.

The prior comment in `chunker.py` *acknowledged* the 256 limit and kept 400
anyway, reasoning that chunks were "sized for the LLM's context, not the
embedder's". That reasoning is wrong in one step: text the embedder truncates can
never be retrieved, so it never reaches the LLM either. It is not extra context,
it is dead weight in the vector.

**Fix:** `TARGET_TOKENS = 150`, `OVERLAP_TOKENS = 25`, and
`test_default_chunks_fit_inside_the_embedder_window` asserts every chunk against
the **live tokenizer** rather than a hardcoded ratio — the ratio is what failed.
`max_knowledge_chunks` 4 → 6, so six 150-token chunks land near the old
four-400 prompt budget.

### 4. A duplicated default that made bug 3's fix inert

Retuning the chunker changed nothing: reindexing still produced 2 chunks.
`ChunkEmbedRequest` restated the defaults as literals:

```python
target_tokens: int = 400   # shadowed chunker.TARGET_TOKENS
overlap_tokens: int = 50
```

Every request arrived carrying the stale values explicitly, so the chunker's own
constants were never consulted by the only caller that matters.

**Fix:** the request model imports `TARGET_TOKENS` / `OVERLAP_TOKENS` instead of
restating them.

## Query composition: measured, then left alone

The call site composes `f"{category} {error_message}"` rather than reusing
`embedding_input()`, which looked like an oversight. It is not — it wins:

| composition | recall @0.40 | false hits |
|-------------|--------------|-----------|
| `f"{cat} {err}"` (current) | 6/6 | 1 |
| `embedding_input(...)`     | 6/6 | 1 (5 at 0.35) |
| `embedding_input` + title-prefixed chunk | 6/6 | 1 |
| bare error, title-prefixed chunk | 6/6 | 1 |

Composition barely moves the result; the threshold and chunk size were the whole
problem. Documentation is human prose, not normalized error rows, so the
`ecosystem: php | job: test` suffix is noise on this side. Left as-is with a
comment recording that it was measured, so the next reader does not "fix" it.

## Verification

End to end against the live database, one indexed runbook, project-scoped:

| query | expected | chunks | top score |
|-------|----------|--------|-----------|
| `SQLSTATE[HY000] [2002] Connection refused` | hit | 1 | 0.557 |
| `php artisan migrate --seed timed out after 600s` | hit | 3 | 0.560 |
| `Redis connection refused during queue tests` | hit | 4 | 0.653 |
| `npm ERR! ERESOLVE unable to resolve dependency tree` | miss | 0 | — |
| `Your branch is behind origin/main by 3 commits` | miss | 0 | — |
| `TypeError: Cannot read properties of undefined` | miss | 0 | — |

6/6 as expected. Before the fixes: 0/3 hits.

## Bug 5: retrieval found the problem, never the fix

With the four bugs above fixed, retrieval worked and the answers were still
generic. Scoring every chunk of the runbook against the error it documents shows
why:

| chunk | similarity | content |
|-------|-----------|---------|
| #0 | **0.573** | `## SQLSTATE[HY000] [2002] Connection refused` — **Symptom.** … |
| #1 | 0.289 | …the job log shows no migration output… |
| #2 | **0.059** | **Fix.** Give the service a healthcheck… `condition: service_healthy` |
| #3 | 0.124 | Do not paper over this with `sleep 10`… |
| #4 | 0.231 | (second section: seeder timeouts) |

The chunk holding the answer is **nearly orthogonal to the query**. This is
structural, not a tuning problem: a runbook is written symptom → cause → fix, and
only the symptom section is phrased in the words of the error. The fix section
describes a remedy, so it shares almost no vocabulary with the failure. No
threshold separates 0.059 from noise — 0.06 would admit every document in the
workspace.

So the model received a restatement of the problem it had just been shown.

**Fix:** neighbour expansion. Chunks that match on similarity are *seeds*; the
chunks around them are fetched too and quoted in document order. The neighbours
of a hit are not extra context, they are the answer.

Radius is a function of chunk size and has to move with it. At 150 tokens a
symptom → cause → fix arc spans about three chunks, and the seed lands on the
symptom, so radius 1 stopped exactly one chunk short of the remedy. Radius 2
reaches it. Ordering is by document, then position — a runbook quoted out of
sequence reads as contradictory advice and the model cannot tell which fragment
came first.

Precision is unaffected: expansion only fires on documents that already had a
seed above threshold, so all four distractor queries still return nothing.

### Measured effect on the answer

Same failure, same model (`gemini-3.6-flash`), same log. Only the retrieved
passage differs:

| | seeds only (1 chunk) | with neighbours (3 chunks) |
|---|---|---|
| root cause | "unable to connect… **likely due to** the database service not being up, running, or reachable on the configured host/port" | "The database container was **not ready to accept connections** when the migration started" |
| recommendation | "Verify database service readiness and status" | "Add a healthcheck to the PostgreSQL service definition in your CI compose file and update the dependent service to wait for `condition: service_healthy`" |
| prompt tokens | 849 | 1150 |
| cost | $0.00203 | $0.00251 |

+$0.0005 and +301 prompt tokens buys the difference between a hedge and the
team's own documented fix, naming the exact compose condition. Still 4× under the
$0.01 per-analysis target.

## Bug 6: the measured values were overridden by `.env`

`max_knowledge_chunks` was raised from 4 to 6 in `config.py`, and the running
service kept using 4 — `.env` and `.env.example` both pinned
`MAX_KNOWLEDGE_CHUNKS=4`. The unit tests caught it: they asserted against
`settings()` and saw the pinned value, not the default.

This is the third instance of one failure mode in this investigation. A value
that exists in two places is not configured, it is duplicated, and the stale copy
always wins:

1. `ChunkEmbedRequest` restated the chunker's defaults as literals.
2. `rag.py` restated the knowledge threshold as a literal `0.60` at the call site.
3. `.env` pinned a retrieval cap the config had moved on from.

Every retrieval knob is now named in `.env.example` with the reason for its
value, so the file that overrides the default also carries the argument for it.

## What is still soft

- The corpus is 9 documents I wrote. Precision 0.86 is measured on 48 pairs, not
  a real knowledge base. Recalibrate once teams have written real runbooks.
- 0.40 is tuned for MiniLM specifically. Changing `embedding_model` invalidates
  both this threshold and `similarity_threshold`, and the chunk size too — the
  window is a property of the model.
- Chunk ordering within a hit set is imperfect: the migration query's top chunk
  is the adjacent "don't use sleep 10" passage. All hits reach the prompt, so
  this costs ranking quality, not correctness.
- **Existing documents must be reindexed** after this change. Old chunks were
  built at 400 tokens and are still truncated in place.

## Lesson

Both retrieval thresholds in this system were guesses, and both guessed a value
that returned nothing. A guessed threshold does not fail loudly — it reports
`chunks=0`, which reads exactly like "nothing relevant". Any similarity cutoff
must ship with the measurement that produced it, and a retrieval path that can
return empty needs a test that would notice if it *always* did.

Six bugs sat between a correctly indexed runbook and an answer that used it, and
not one of them raised an error. Four made retrieval return nothing, one returned
the wrong half of the document, and one silently overrode the fix. The feature
reported success at every step; only the quality of the answer was worse, which
is the hardest kind of failure to notice and the easiest to attribute to "the
model is not very good".

The general lesson is about what "working" means. Every stage here was
individually healthy — the document indexed, the query embedded, the search ran,
the prompt rendered — and the pipeline as a whole did nothing. Retrieval needs an
end-to-end assertion that a known document is actually reachable from a known
error, because no unit test on any single stage would have caught this.
