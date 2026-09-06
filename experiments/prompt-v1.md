# Analysis prompt — v1

**Frozen:** 2026-09-06 · **Template:** `PipeMind-ai/app/prompts/analyze.j2` ·
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

## Measurements to fill in on real data

Deliberately left blank — the numbers belong to the run, not the design.

| Metric | Target | v1 |
|---|---|---|
| Analysis latency p50 | < 6 s | — |
| Cost per analysis | < $0.01 | — |
| Evidence items with a valid `source_ref` | 100% | — |
| Invalid JSON from a schema-constrained provider | 0 | — |
| Root cause judged correct on the 5 fixtures | 5/5 | — |

Fill these in after the first real Gemini runs, then compare against v2.

## Known limitations of v1

- The excerpt is capped and the model never sees the full log; a cause outside
  the extracted window is invisible to it.
- `changed_files` carries paths and line counts, not diffs. The model can say
  *which* file is implicated but not *which line* of it.
- Knowledge chunks are retrieved by embedding similarity alone — no reranking.
- Confidence is calibrated after the fact in `_calibrate()` rather than the model
  being trained to be calibrated. It is a correction, not a cure.
