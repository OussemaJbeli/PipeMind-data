# Group 6 — Vectors & Knowledge

`failure_embeddings` · `knowledge_documents` · `knowledge_chunks`

## Purpose

Similarity search over past failures, and retrieval over project documentation. This is
what lets PipeMind say *"this resembles a failure from three months ago"* instead of
*"HTTP 401 usually means authentication failed"*.

## Key decisions

**384 dimensions, `all-MiniLM-L6-v2`, local.** Runs on CPU in single-digit milliseconds,
~90 MB, no API key, no internet. Embeddings are independent of the LLM choice — you can
use cloud reasoning with local embeddings, which is the default configuration.

**`model` column + `UNIQUE(failure_id, model)`.** This is the escape hatch from the one
genuinely hard-to-reverse decision in the schema. It lets a second embedding model be
backfilled alongside the first, compared on the same holdout set, and cut over — no
migration, no data loss. **Do not remove this column.**

**HNSW, not IVFFlat.** Better recall at this scale and no training step, so the index
works correctly from the first row.

**What gets embedded matters more than which model.** Embedding the raw 40-line excerpt
gives a similarity landscape dominated by log formatting — everything ends up 0.8-similar
to everything. `embedding_input()` composes the *normalised error* plus category,
ecosystem and job name instead.

## Retrieval ordering

Nearest-neighbour search orders by **resolution first, distance second**:

```sql
ORDER BY (f.resolved_at IS NOT NULL) DESC, fe.embedding <=> :query
```

A 0.94-similar failure nobody ever fixed teaches nothing. A 0.88-similar failure with a
confirmed resolution is the entire point of having history. Retrieval quality here is
usefulness, not raw closeness.

## Gotchas

- `normalize_embeddings=True` at encode time — cosine distance assumes unit vectors.
- The 0.75 similarity threshold is a starting guess. Calibrate it against labelled
  same-cause / different-cause pairs. If everything scores above 0.9, the embedding input
  is too generic.
- Knowledge chunks are ~400 tokens with 50-token overlap. Chunks that split a code block
  in half retrieve badly.
