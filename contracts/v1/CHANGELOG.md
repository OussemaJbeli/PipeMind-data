# Contract v1 — changelog

The shapes in this directory are the agreement between Laravel (`PipeMind-back`)
and the AI service (`PipeMind-ai`). They are generated from the Pydantic models,
never hand-edited:

```bash
cd PipeMind-ai && ./.venv/bin/python scripts/export_contracts.py
```

## Versioning rule

Additive changes — a **new optional field** — stay in `v1`. Anything that removes
a field, renames one, or changes a type creates `v2`, and both run side by side
until Laravel has migrated.

`contract_version` travels in every request and response, so a mismatch is a loud
error rather than a silent wrong answer.

## Why this is generated, not written

Laravel cannot see Python type hints. Without an exported schema, the only place
the contract exists is in two codebases that have no way to compare themselves —
and a breaking change shows up as a 422 in production instead of a diff in
review.

---

## 2026-09-06 — initial export

Fourteen schemas covering every `/v1` endpoint.

| Endpoint | Request | Response |
|---|---|---|
| `POST /v1/logs/process` | `logs-process.request.json` | `logs-process.response.json` |
| `POST /v1/classify` | `classify.request.json` | `classify.response.json` |
| `POST /v1/analyze` | `analyze.request.json` | `analyze.response.json` |
| `POST /v1/embed` | `embed.request.json` | `embed.response.json` |
| `POST /v1/similar` | `similar.request.json` | *(array of `SimilarFailure`)* |
| `POST /v1/knowledge/chunk-embed` | `knowledge-chunk-embed.request.json` | `knowledge-chunk-embed.response.json` |
| `POST /v1/providers/test` | `providers-test.request.json` | `providers-test.response.json` |
| `GET /v1/info` | — | `info.response.json` |

### Fields added during files 09–10, all optional and therefore still `v1`

- `AnalyzeRequest.failure.ecosystem` — detected at ingestion and folded into the
  signature hash. Retrieval must compose the same embedding input the signature
  was hashed with, and without this it could not.
- `AnalyzeRequest.force_llm` — bypasses the known-signature short-circuit. Sent by
  "Re-analyze" when a user disputes a stored resolution.
- `EmbedRequest.category` / `.ecosystem` / `.job_name` — so a text embedded here
  is composed the same way retrieval composes it, and the two are comparable.
- `EmbedResponse.source_text` — echoes what was actually embedded, so Laravel
  stores that rather than what it sent.
- `ServiceInfo.embeddings_ready` / `.providers` — a misconfigured key shows as a
  red dot in the UI instead of a failed analysis an hour later.

## 2026-09-07 — additive

- `AnalyzeRequest.project.id` — the numeric project id. `knowledge_documents.project_id`
  is a bigint and the AI service reads that table directly, so project-scoped
  retrieval needs the id; the contract carried only `uuid`, which is why the
  analyzer passed `project_id=None` and project runbooks were unreachable.
  Optional: a payload without it degrades to team-wide knowledge rather than failing.
- `ChunkEmbedRequest.target_tokens` default 400 → 150, `.overlap_tokens` 50 → 25.
  Not a preference: 400 exceeded the embedding model's 256 word-piece window, so a
  third of every chunk was truncated before it was ever embedded. Callers that
  send these fields explicitly should stop — the defaults now track
  `chunker.TARGET_TOKENS`. **Documents indexed before this change must be
  reindexed**; their chunks are still stored at the old boundaries.
