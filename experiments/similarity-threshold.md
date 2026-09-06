# Similarity threshold — first pass

**Run:** 2026-09-06 · **Model:** `sentence-transformers/all-MiniLM-L6-v2` (384-dim, unit-normalised)
**Distance:** cosine (`<=>` in pgvector, similarity = 1 − distance)

## Why this was run

Roadmap 09 set `SIMILARITY_THRESHOLD=0.75` as an explicit starting guess, with a
note to calibrate it against real data. The guess turned out to be unusable, and
the way it failed is worth recording.

## Headline finding

**At 0.75, retrieval returns nothing. Ever.**

Across ten pairs of realistic CI failures, the highest similarity observed was
**0.5865**. Not one pair reached 0.75, including the pair that genuinely shares a
root cause.

This is the dangerous kind of bug. Nothing errors, nothing logs, no test fails —
`similar_failures` is simply always `[]`, `used_rag` is always `false`, and the
"learns from your history" feature does nothing at all while looking exactly like
a workspace that has no history yet. It would have survived to production and
been discovered, if ever, as "the similar-failures panel is always empty".

## Experiment 1 — what to embed

Five failures, of which exactly one pair shares a root cause: the database is
unreachable, seen once through Laravel (`SQLSTATE[HY000] [2002] Connection
refused`) and once through Node (`connect ECONNREFUSED 127.0.0.1:5432`). Two
strategies compared:

| Strategy | Same-cause pair | Mean unrelated | Max unrelated | Separation |
|---|---|---|---|---|
| Raw 40-line log excerpt | 0.4273 | 0.3513 | 0.6552 | **−0.2280** |
| Composed input (`error \| category \| ecosystem \| job`) | 0.5772 | 0.4437 | 0.5865 | **−0.0094** |

Separation = same-cause similarity − most-similar unrelated pair. Positive means
the true match ranks first; negative means something unrelated outranks it.

**Composing the input improves separation by +0.22.** The roadmap's claim holds:
embedding the raw excerpt makes log *formatting* the dominant signal, and two
failures written in the same log style score more alike than two failures with
the same cause.

But note that both numbers are negative. Composing helps a great deal and still
does not, on its own, put the true match first.

## Experiment 2 — the full pair matrix (composed input)

```
0.5865  db-refused-node    ~ npm-peer-conflict
0.5772  db-refused-laravel ~ db-refused-node     ← the only true match
0.5294  db-refused-node    ~ assert-fail
0.5222  db-refused-laravel ~ assert-fail
0.5166  npm-peer-conflict  ~ oom
0.4257  db-refused-node    ~ oom
0.3864  oom                ~ assert-fail
0.3812  npm-peer-conflict  ~ assert-fail
0.3403  db-refused-laravel ~ npm-peer-conflict
0.3052  db-refused-laravel ~ oom
```

The top-ranked pair is wrong, and it is wrong in an instructive way: a Node
database failure and a Node dependency failure score 0.5865 because **they are
both Node**. The `ecosystem: node` token — added to sharpen the vector — became
a similarity floor between everything sharing a runtime.

## What changed as a result

**1. Threshold 0.75 → 0.55.** Provisional, not calibrated. 0.55 admits the true
pair (0.5772) and one false positive (0.5865); 0.60 admits nothing. Given the
alternative is guaranteed zero recall, a low-precision threshold that at least
surfaces candidates is the better failure mode — especially since the model sees
each neighbour's category, similarity percentage, and resolution status, and the
prompt instructs it to treat unresolved neighbours as context rather than fixes.

**2. Same-category neighbours now rank above closer cross-category ones.**
`find_similar_failures` orders by:

```sql
ORDER BY
    (f.resolved_at IS NOT NULL) DESC,   -- a resolved neighbour teaches more
    (f.category = :category) DESC,       -- ... in the same category
    fe.embedding <=> CAST(:emb AS vector)
```

A hard `WHERE category = :category` filter was considered and rejected: a DOCKER
failure can genuinely present as a DATABASE symptom, and a hard filter would make
that case unreachable. Ranking preserves it while ensuring a same-category
neighbour is never outranked by the ecosystem-token artefact above.

## Limits of this experiment — read before quoting it

- **Five handcrafted failures, one true pair.** This is directional evidence, not
  calibration. "0.5865 > 0.5772" is one pair of numbers, not a precision figure.
- **The threshold is not the main defence against recurrence.** Identical errors
  are caught upstream by `failure_signature`, exactly and for free. The
  similarity layer exists for *related but not identical* failures, which is the
  harder case and the one measured here.
- **No labelled corpus yet.** The proper calibration described in roadmap 09 —
  100 human-labelled same/different pairs, plot both distributions, take the
  crossover — needs real data from real usage.

## Next pass

1. Collect ≥100 labelled pairs from `analysis_feedback` once the app has real use.
2. Plot the same-cause and different-cause distributions; set the threshold at
   the crossover; report precision@5 and recall.
3. Test dropping `ecosystem` from `embedding_input` — it may be causing more
   collisions than it prevents, now that category is a ranking key.
4. Compare `all-MiniLM-L6-v2` against a larger model (`all-mpnet-base-v2`,
   768-dim) on the same labelled set. `failure_embeddings.model` and its
   `UNIQUE (failure_id, model)` exist precisely so both can be stored and
   compared before any cutover.
