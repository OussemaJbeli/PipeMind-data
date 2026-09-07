# Analysis prompt — v1

**Frozen:** 2026-09-06 · **Measured against Gemini:** 2026-09-06 · **Template:** `PipeMind-ai/app/prompts/analyze.j2` ·
**System prompt + schema:** `PipeMind-ai/app/services/prompts.py`

Recorded so that a later change in analysis quality can be attributed to the
prompt rather than guessed at. Any edit to the template, the system prompt or
the schema starts a v2 file; this one is not edited again.

---

## System prompt (785 chars)

The five rules, and why each is there:

| Rule | Failure it prevents |
|---|---|
| Ground every claim in the evidence provided | Invented file names and line numbers — the single most damaging failure mode, because a fabricated citation looks checkable |
| Distinguish what you OBSERVE from what you INFER | An inference presented as a fact that the user then acts on |
| Lower confidence when evidence is thin | Uniform 0.95 confidence, which makes the number worthless |
| Prefer the simplest explanation | Elaborate causal chains where "the service wasn't started" would do |
| Lead with a matching confirmed resolution | Re-deriving an answer the workspace already paid to learn |

The recommendation rule ("never recommend an action that could destroy data or
affect production without explicit human review") is belt-and-braces only. It is
a request, and a model can decline a request — so risk is *also* assigned in code
from `action_type`, in `app/services/recommender.py`. The prompt is the polite
version; the sanitiser is the enforced one.

## Prompt structure

Ordered by what a reader would need first, because attention degrades over
length and the top of the prompt is the most expensive real estate:

1. **Failure** — project, branch (flagged when it is the default), stage, job, exit code
2. **Pre-classification** — the rule engine's verdict, its confidence, the rules that fired
3. **Files changed in this commit** — config and dependency files flagged
4. **Timing** — duration against the job's own baseline
5. **Log excerpt** — redacted, with line numbers so citations can be checked
6. **Stack trace** — when one was extracted
7. **KNOWN ISSUE** — only when the signature has a confirmed resolution
8. **Similar past failures** — with resolutions, and unresolved ones marked `(never resolved)`
9. **Project documentation** — retrieved runbook chunks
10. **Task**

Sections 7–9 are omitted entirely rather than rendered empty. An empty
"Similar past failures" heading reads as *nothing is similar*, which is a claim
the retrieval layer never made.

## Design decisions worth defending

**The classifier's verdict goes in the prompt.** Anchoring is the point: the
rule engine is deterministic and often right, and the model does better
confirming or contradicting a stated hypothesis than starting cold. The model
may still override the category — when it does, that disagreement is worth
looking at.

**Unresolved neighbours are labelled.** A 91%-similar failure nobody ever fixed
is context, not a solution. Without the label the model presents it as one.

**Line numbers on the excerpt.** Evidence carries a `source_ref`; the numbers are
what makes it verifiable rather than decorative.

**Baseline duration, not absolute duration.** "92 s" means nothing. "92 s against
a 41 s baseline" means a timeout or a hang.

**Schema-constrained decoding where the provider supports it** (Gemini,
OpenAI-compatible). Invalid JSON becomes impossible rather than handled. Ollama
has no such guarantee, so `salvage_json()` covers bare, fenced and prose-wrapped
output there.

## Measurements — first real Gemini run

**Measured 2026-09-06** · `gemini-3.6-flash`, `thinking_level=low`, 7 real failures
spanning 7 categories, one analysis each, service warm.

| Metric | Target | v1 measured |
|---|---|---|
| Analysis latency p50 | < 6 s | **4.14 s** ✓ |
| Analysis latency min / max | — | 3.11 s / 6.76 s |
| Cost per analysis (mean) | < $0.01 | **$0.001495** ✓ |
| Cost per analysis (max) | < $0.01 | $0.001993 ✓ |
| Evidence items with a valid `source_ref` | 100% | **15/15** ✓ |
| Invalid JSON from a schema-constrained provider | 0 | **0** ✓ |
| LLM category agreed with the rule classifier | — | **7/7** |
| Prompt size | — | 522–660 tokens |

Per-category detail:

| Ingest category | LLM category | Latency | Cost | in/out tokens | Evidence | Recos |
|---|---|---|---|---|---|---|
| NETWORK | NETWORK | 4140 ms | $0.001317 | 522 / 464 | 2 | 1 |
| BUILD | BUILD | 6759 ms | $0.001609 | 556 / 577 | 2 | 2 |
| TEST | TEST | 5846 ms | $0.001986 | 587 / 724 | 3 | 2 |
| DOCKER | DOCKER | 3706 ms | $0.001221 | 636 / 412 | 2 | 1 |
| DATABASE | DATABASE | 5065 ms | $0.001993 | 609 / 724 | 2 | 2 |
| DEPENDENCY | DEPENDENCY | 3793 ms | $0.001406 | 660 / 483 | 2 | 1 |
| CONFIGURATION | CONFIGURATION | 3111 ms | $0.000933 | 552 / 307 | 2 | 1 |

Cost is **6.7× under budget**, which makes the caching layer a convenience rather
than a necessity at this scale — worth stating plainly rather than overselling it.

### Grounding held

Every citation was checked against the input by hand for the DATABASE case:

- `DatabaseTest.php:42` — present in the log excerpt ✓
- `docker-compose.yml` — present in `changed_files` ✓
- `SQLSTATE[HY000] [2002] Connection refused` — present in the log excerpt ✓

Nothing was invented. The model also volunteered an explicit `OBSERVED: … INFERRED: …`
split inside `explanation` without being asked to structure it that way — the
system prompt's second rule reached the output.

### `thinking_level` is the whole latency story

Gemini 3.x reasons before answering, and those tokens are billed as output while
never appearing in the response. On one fixture:

| thinking_level | Latency | Thinking tokens | Valid JSON |
|---|---|---|---|
| `high` | 16.4 s | 2330 | yes |
| unset (default) | 11.1 s | 1462 | yes |
| **`low`** | **3.2 s** | **0** | yes |

`low` is the default in `GEMINI_THINKING_LEVEL`. CI failure analysis is a
short-context, heavily-grounded task where the rule classifier has already
narrowed the category — the extra reasoning buys little here. Raise it for a
project whose failures are genuinely ambiguous.

Counting thinking tokens as output matters: excluding them understated cost by
roughly 4× at the default level. `GeminiProvider` now adds
`thoughts_token_count` into `completion_tokens`.

### Caveats

- Seven failures, one run each. p50 from n=7 is indicative, not a distribution.
- All seven are seeded fixtures with clean, short logs. Real 5000-line logs will
  push prompt tokens and latency up.
- Rates in `ai_providers` are placeholders (input $0.0003/1k, output $0.0025/1k)
  and must be checked against https://ai.google.dev/pricing. Every cost figure
  above scales linearly with them.
- One run hit `429 RESOURCE_EXHAUSTED` on the free tier. That path is handled
  (`LLMRateLimited`, retryable, with backoff), but free-tier quota — not the
  monthly budget — is the first ceiling this project will actually meet.

## Known limitations of v1

- The excerpt is capped and the model never sees the full log; a cause outside
  the extracted window is invisible to it.
- `changed_files` carries paths and line counts, not diffs. The model can say
  *which* file is implicated but not *which line* of it.
- Knowledge chunks are retrieved by embedding similarity alone — no reranking.
- Confidence is calibrated after the fact in `_calibrate()` rather than the model
  being trained to be calibrated. It is a correction, not a cure.
