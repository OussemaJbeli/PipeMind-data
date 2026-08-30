# 09 — LLM, Embeddings & RAG

**Repo:** `PipeMind-ai` · **Depends on:** 08 · **Milestone:** M3 (LLM) + M4 (RAG)

The reasoning layer: provider abstraction, structured output, prompt construction, embeddings, pgvector similarity, retrieval-augmented context, and the analyzer that orchestrates the whole pipeline into one `AnalyzeResponse`.

---

## 9.1 Provider abstraction

Nothing outside `app/providers/` may import a vendor SDK.

```python
# ready — app/providers/base.py
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    parsed: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    provider: str = ""
    latency_ms: int = 0
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: int = 90,
    ) -> LLMResponse: ...

    async def health(self) -> bool: ...

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float: ...
```

```python
# ready — app/providers/gemini.py
import json
import time

from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.errors import InvalidLLMResponse, LLMRateLimited, LLMTimeout, LLMUnavailable
from app.providers.base import LLMResponse


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash",
                 input_cost_per_1k: float = 0.0, output_cost_per_1k: float = 0.0) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._in = input_cost_per_1k
        self._out = output_cost_per_1k

    @retry(
        retry=retry_if_exception_type((LLMRateLimited, LLMTimeout)),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(self, *, system: str, prompt: str, json_schema: dict | None = None,
                       temperature: float = 0.2, max_tokens: int = 4096,
                       timeout: int = 90) -> LLMResponse:
        started = time.perf_counter()

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
            # Schema-constrained decoding: the model cannot emit invalid JSON.
            # This removes an entire class of parse-and-retry failure.
            response_mime_type="application/json" if json_schema else "text/plain",
            response_schema=json_schema,
        )

        try:
            res = await self._client.aio.models.generate_content(
                model=self._model, contents=prompt, config=config
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "rate" in msg or "429" in msg or "quota" in msg:
                raise LLMRateLimited(str(exc)) from exc
            if "timeout" in msg or "deadline" in msg:
                raise LLMTimeout(str(exc)) from exc
            raise LLMUnavailable(str(exc)) from exc

        text = res.text or ""
        parsed = None

        if json_schema:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InvalidLLMResponse(f"non-JSON despite schema: {text[:200]}") from exc

        usage = res.usage_metadata

        return LLMResponse(
            text=text,
            parsed=parsed,
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            model=self._model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def health(self) -> bool:
        try:
            await self.complete(system="reply with ok", prompt="ok", max_tokens=8, timeout=10)
            return True
        except Exception:  # noqa: BLE001
            return False

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return round(prompt_tokens / 1000 * self._in + completion_tokens / 1000 * self._out, 6)
```

```python
# ready — app/providers/openai_compatible.py
# Covers OpenAI, Azure OpenAI, Ollama's /v1 endpoint, vLLM, LM Studio, OpenRouter —
# one implementation for every provider that speaks the OpenAI chat schema.
from openai import AsyncOpenAI


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, api_key: str, model: str, base_url: str | None = None,
                 input_cost_per_1k: float = 0.0, output_cost_per_1k: float = 0.0) -> None:
        self._client = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url)
        self._model = model
        self._in, self._out = input_cost_per_1k, output_cost_per_1k

    async def complete(self, *, system, prompt, json_schema=None, temperature=0.2,
                       max_tokens=4096, timeout=90) -> LLMResponse:
        started = time.perf_counter()

        kwargs: dict = {
            "model": self._model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }

        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "analysis", "schema": json_schema, "strict": True},
            }

        res = await self._client.chat.completions.create(**kwargs)
        # … map to LLMResponse, same error taxonomy as Gemini
```

```python
# ready — app/providers/ollama.py
# Ollama exposes an OpenAI-compatible API at {base_url}/v1, but its JSON mode is
# "format": "json" — a hint, not a constraint. Local models WILL sometimes emit
# prose around the JSON, so the parser must be forgiving where Gemini's is not.
import re

FENCED = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```")
BRACES = re.compile(r"\{[\s\S]*\}")


def salvage_json(text: str) -> dict | None:
    """Recover JSON from a local model's chattier output."""
    for candidate in (
        (m.group(1) if (m := FENCED.search(text)) else None),
        (m.group(0) if (m := BRACES.search(text)) else None),
        text.strip(),
    ):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None
```

> **Schema-constrained decoding is the difference between a demo and a product.** With Gemini or OpenAI structured outputs, invalid JSON is impossible by construction. With Ollama it is merely unlikely, so `salvage_json` plus one repair retry is required. Report this asymmetry honestly in your evaluation — it is a real cost of the local option.

```python
# ready — app/providers/registry.py
from app.config import settings
from app.core.errors import LLMUnavailable


def build_provider(override: dict | None = None):
    """Resolve a provider from the team's ai_providers row, falling back to env defaults.

    `override` is passed through by Laravel so each team can use its own key and model
    without the AI service holding any team's credentials at rest.
    """
    cfg = settings()
    o = override or {}
    kind = o.get("provider") or cfg.llm_provider

    if kind == "gemini":
        key = o.get("api_key") or cfg.gemini_api_key
        if not key:
            raise LLMUnavailable("No Gemini API key configured")
        return GeminiProvider(key, o.get("model") or cfg.gemini_model,
                              o.get("input_cost_per_1k", 0.0), o.get("output_cost_per_1k", 0.0))

    if kind == "ollama":
        return OllamaProvider(o.get("base_url") or cfg.ollama_base_url,
                              o.get("model") or cfg.ollama_model)

    if kind in ("openai", "openai_compatible", "azure_openai"):
        return OpenAICompatibleProvider(
            o.get("api_key") or cfg.openai_api_key or "",
            o.get("model") or cfg.openai_model,
            o.get("base_url") or cfg.openai_base_url,
            o.get("input_cost_per_1k", 0.0), o.get("output_cost_per_1k", 0.0),
        )

    raise LLMUnavailable(f"Unknown provider: {kind}")
```

### Provider fallback

A team can configure a fallback so a cloud outage degrades instead of failing.

```python
# ready — app/providers/registry.py
async def build_provider_with_fallback(override: dict | None = None):
    """Primary provider, with an optional local fallback.

    Only failures that a different provider could plausibly fix trigger the
    fallback: unavailability, timeouts, rate limits. A malformed response or a
    budget stop is not a network problem and must surface as itself.
    """
    primary = build_provider(override)

    fallback_cfg = (override or {}).get("fallback")
    if not fallback_cfg:
        return primary

    return FallbackProvider(primary, build_provider(fallback_cfg))


class FallbackProvider:
    name = "fallback"

    def __init__(self, primary, secondary) -> None:
        self._primary, self._secondary = primary, secondary

    async def complete(self, **kwargs) -> LLMResponse:
        try:
            return await self._primary.complete(**kwargs)
        except (LLMUnavailable, LLMTimeout, LLMRateLimited) as exc:
            log.warning("llm.fallback", primary=self._primary.name,
                        secondary=self._secondary.name, reason=type(exc).__name__)
            res = await self._secondary.complete(**kwargs)
            res.raw["fell_back_from"] = self._primary.name
            return res
```

> **Never fall back silently.** `analyses.model_provider` records which provider actually produced the result, and the UI's provenance strip (file 16) shows it. An analysis produced by a 3B local model when the user expected Gemini is not wrong — but presenting it as though nothing changed is. Log it, store it, show it.

Do not fall back on `InvalidLLMResponse` (a second model will likely fail the same way on the same input) or on `BudgetExceeded` (the point of a budget is that it stops you).

**Pricing** lives in the `ai_providers` row (`input_cost_per_1k` / `output_cost_per_1k`), not in code. Rates change; a hardcoded number becomes a lie in a month. Fill each provider's row from its current pricing page when you add it, and record the date you checked in `settings`.

- [ ] Four provider implementations + registry
- [ ] `respx`-mocked tests for success, rate limit, timeout, malformed JSON
- [ ] `/v1/info` reports live provider health

---

## 9.2 Embeddings

```python
# ready — app/services/embeddings.py
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Loaded once at boot (see main.py lifespan). ~90 MB, ~8 s cold."""
    return SentenceTransformer(settings().embedding_model, device="cpu")


def embed_text(text: str) -> list[float]:
    vec = get_embedder().encode(
        _prepare(text),
        normalize_embeddings=True,   # cosine distance assumes unit vectors
        show_progress_bar=False,
    )
    return np.asarray(vec, dtype=np.float32).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    vecs = get_embedder().encode(
        [_prepare(t) for t in texts],
        batch_size=settings().embedding_batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [np.asarray(v, dtype=np.float32).tolist() for v in vecs]


def _prepare(text: str) -> str:
    """all-MiniLM truncates at 256 word-pieces. Choose those 256 deliberately."""
    return " ".join(text.split())[:1000]


def embedding_input(*, error_message: str, category: str | None,
                    ecosystem: str | None, job_name: str | None) -> str:
    """Compose what actually gets embedded.

    Raw log excerpts embed badly — timestamps, paths and IDs dominate the vector
    and everything ends up 0.8-similar to everything else. Embed the normalized
    error plus a little structured context instead.
    """
    parts = [error_message.strip()[:600]]
    if category:
        parts.append(f"category: {category}")
    if ecosystem:
        parts.append(f"ecosystem: {ecosystem}")
    if job_name:
        parts.append(f"job: {job_name}")
    return " | ".join(parts)
```

> **What you embed matters more than which model you use.** Embedding the raw 40-line excerpt gives you a similarity landscape dominated by log formatting. Embedding the *normalized error* plus category and ecosystem gives you neighbours that actually share a root cause. Test both and put the comparison in your report — it is a cheap, genuinely interesting experiment.

- [ ] `embeddings.py` implemented
- [ ] `/v1/embed` returns a 384-dim unit vector
- [ ] `EmbedFailure` job in Laravel writes to `failure_embeddings` after every analysis

---

## 9.3 Similarity

```python
# ready — app/services/similarity.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.queries import find_similar_failures
from app.models.responses import SimilarFailure
from app.services.embeddings import embed_text, embedding_input


async def find_similar(
    session: AsyncSession, *, team_id: int, error_message: str,
    category: str | None = None, ecosystem: str | None = None,
    job_name: str | None = None, exclude_failure_id: int | None = None,
    limit: int | None = None, threshold: float | None = None,
) -> list[SimilarFailure]:
    cfg = settings()

    vector = embed_text(embedding_input(
        error_message=error_message, category=category,
        ecosystem=ecosystem, job_name=job_name,
    ))

    rows = await find_similar_failures(
        session, team_id=team_id, embedding=vector,
        limit=limit or cfg.max_similar_failures,
        threshold=threshold or cfg.similarity_threshold,
        exclude_failure_id=exclude_failure_id,
    )

    return [
        SimilarFailure(
            uuid=r["uuid"],
            similarity=round(float(r["similarity"]), 4),
            project_name=r["project_name"],
            occurred_at=r["failed_at"].isoformat(),
            root_cause=r["known_root_cause"],
            resolution=r["known_resolution"] or r["resolution_note"],
            resolved=r["resolved_at"] is not None,
        )
        for r in rows
    ]
```

**Threshold calibration** — do this once with real data, don't guess:

```python
# spec — scripts/calibrate_similarity.py
# 1. Take 100 failure pairs a human labeled same-root-cause / different-root-cause.
# 2. Compute cosine similarity for each pair.
# 3. Plot the two distributions; pick the threshold at their crossover.
# 4. Report precision@k and recall at the chosen threshold.
# Commit to PipeMind-data/experiments/similarity-threshold.md
```

0.75 is a starting guess. Real data usually moves it. If everything scores above 0.9, your embedding input is too generic — go back to `embedding_input`.

- [ ] `/v1/similar` live
- [ ] Threshold calibrated against labeled pairs, documented

---

## 9.4 RAG

```python
# ready — app/services/rag.py
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.queries import find_knowledge_chunks, get_signature_history
from app.models.responses import SimilarFailure
from app.services.embeddings import embed_text
from app.services.similarity import find_similar


@dataclass
class RetrievedContext:
    similar_failures: list[SimilarFailure] = field(default_factory=list)
    knowledge_chunks: list[dict] = field(default_factory=list)
    signature_history: dict | None = None
    used: bool = False

    def is_empty(self) -> bool:
        return not (self.similar_failures or self.knowledge_chunks or self.signature_history)


async def retrieve(
    session: AsyncSession, *, team_id: int, project_id: int | None,
    error_message: str, category: str | None, ecosystem: str | None,
    job_name: str | None, signature_hash: str | None,
    exclude_failure_id: int | None = None,
) -> RetrievedContext:
    cfg = settings()

    # 1. Exact signature match short-circuits everything. If this precise error
    #    already has a confirmed resolution, retrieval is done — and the LLM's job
    #    becomes "confirm and explain", not "guess".
    history = (await get_signature_history(session, team_id, signature_hash)
               if signature_hash else None)

    if history and history.get("is_known"):
        return RetrievedContext(signature_history=history, used=True)

    # 2. Nearest historical failures
    similar = await find_similar(
        session, team_id=team_id, error_message=error_message, category=category,
        ecosystem=ecosystem, job_name=job_name, exclude_failure_id=exclude_failure_id,
    )

    # 3. Project documentation / runbooks
    query_vec = embed_text(f"{category or ''} {error_message}"[:1000])
    chunks = await find_knowledge_chunks(
        session, team_id=team_id, project_id=project_id,
        embedding=query_vec, limit=cfg.max_knowledge_chunks, threshold=0.60,
    )

    return RetrievedContext(
        similar_failures=similar,
        knowledge_chunks=chunks,
        signature_history=history,
        used=bool(similar or chunks or history),
    )
```

- [ ] `rag.py` implemented
- [ ] Knowledge ingestion: chunk documents at ~400 tokens with 50-token overlap, embed, store in `knowledge_chunks`

---

## 9.5 Prompts

```jinja
{# ready — app/prompts/analyze.j2 #}
{# SYSTEM #}
You are PipeMind, a CI/CD failure analyst. You explain why pipelines fail.

Rules you must follow:
- Ground every claim in the evidence provided. Never invent file names, line numbers,
  package versions, or error text that does not appear in the input.
- Distinguish what you OBSERVE from what you INFER. State inferences as inferences.
- If the evidence does not support a confident conclusion, say so and lower your confidence.
  A calibrated 0.55 is more useful than a fabricated 0.95.
- Prefer the simplest explanation consistent with all the evidence.
- When a historical failure with a confirmed resolution matches, lead with it.
- Recommendations must be concrete and safe. Never recommend an action that could
  destroy data or affect production without explicit human review.

{# USER #}
## Failure

Project: {{ project.name }}
Stack: {{ project.tech_stack | join(', ') }}
Branch: {{ pipeline.ref }}{% if pipeline.ref == project.default_branch %} (default branch){% endif %}
Stage: {{ job.stage_name }}  ·  Job: {{ job.name }}
Exit code: {{ job.exit_code | default('unknown') }}
{% if failure.occurrence_index > 1 %}
This is occurrence #{{ failure.occurrence_index }} of this exact error in this project.
{% endif %}
{% if failure.is_flaky %}
NOTE: previously observed passing on this same commit — likely flaky.
{% endif %}

## Pre-classification
{{ classification.category }}{% if classification.subcategory %} / {{ classification.subcategory }}{% endif %}
(confidence {{ classification.confidence }}, method: {{ classification.source }})
{% if classification.matched_rules %}Matched patterns: {{ classification.matched_rules | join(', ') }}{% endif %}

Treat this as a strong prior. Override it only if the evidence clearly contradicts it,
and say why if you do.

{% if pipeline.changed_files %}
## Files changed in this commit
{% for f in pipeline.changed_files[:20] %}
- {{ f.path }} ({{ f.change_type }}, +{{ f.additions }}/-{{ f.deletions }}){% if f.is_config %} [CONFIG]{% endif %}{% if f.is_dependency %} [DEPENDENCY]{% endif %}
{% endfor %}
{% if pipeline.previous_status == 'success' %}
The previous pipeline on this branch SUCCEEDED. This change is a strong regression candidate.
{% endif %}
{% endif %}

{% if job.baseline_duration_seconds %}
## Timing
This job took {{ job.duration_seconds }}s. Its normal duration is
{{ job.baseline_duration_seconds | round | int }}s
({{ (job.duration_seconds / job.baseline_duration_seconds) | round(1) }}× baseline).
{% endif %}

## Log excerpt
Lines {{ log.start_line }}–{{ log.end_line }} of {{ log.total_lines }}.
Secrets have been redacted; [REDACTED_*] markers are placeholders, not the actual error.

```
{{ log.excerpt }}
```

{% if stack_trace %}
## Stack trace
```
{{ stack_trace }}
```
{% endif %}

{% if rag.signature_history and rag.signature_history.is_known %}
## KNOWN ISSUE — this exact error signature has a confirmed resolution
Seen {{ rag.signature_history.occurrence_count }} times.
Root cause: {{ rag.signature_history.known_root_cause }}
Resolution: {{ rag.signature_history.known_resolution }}

Verify this matches the current evidence. If it does, lead with it and set confidence high.
{% endif %}

{% if rag.similar_failures %}
## Similar past failures in this workspace
{% for s in rag.similar_failures %}
- {{ (s.similarity * 100) | round | int }}% similar · {{ s.project_name }} · {{ s.occurred_at[:10] }}
  {% if s.root_cause %}Root cause: {{ s.root_cause }}{% endif %}
  {% if s.resolution %}Resolved by: {{ s.resolution }}{% else %}(never resolved){% endif %}
{% endfor %}
{% endif %}

{% if rag.knowledge_chunks %}
## Project documentation
{% for c in rag.knowledge_chunks %}
--- {{ c.title }} ---
{{ c.content }}
{% endfor %}
{% endif %}

## Task
Analyse this failure and respond with JSON matching the provided schema.

For `evidence`, cite only things present above. Use `source_ref` to point at the
origin: "job_logs#L1294" for a log line, the file path for a changed file,
"failure:<uuid>" for a historical failure.

Set `is_transient` true only for failures that would plausibly succeed on an
unchanged retry — network blips, registry timeouts, runner loss. A code or
configuration error is never transient.
```

**Prompt design decisions worth defending in your report:**

| Decision | Why |
|---|---|
| Classification passed in as a prior | The LLM does root-cause reasoning; classification is already solved more cheaply. Don't pay twice. |
| Explicit "previous pipeline succeeded" | Single highest-signal fact available. Regression vs pre-existing is most of the diagnosis. |
| Redaction markers explained | Otherwise the model reasons about `[REDACTED_JWT]` as though it were the literal token value. |
| Line numbers in the excerpt | Enables real `source_ref` values, which makes evidence clickable in the UI. |
| Known-issue block placed last | Recency bias is real; the most decisive context goes closest to the task. |
| Explicit permission to be unsure | Models default to confident. Calibration has to be asked for. |

- [ ] `analyze.j2`, `classify.j2`, `recommend.j2` written
- [ ] Prompts versioned — a prompt change is an experiment, record it in `experiments/`

---

## 9.6 The analyzer

```python
# ready — app/services/analyzer.py
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.budget import assert_within_budget
from app.core.errors import InvalidLLMResponse
from app.models.requests import AnalyzeRequest
from app.models.responses import AnalyzeResponse, Evidence, Recommendation, Usage
from app.providers.registry import build_provider
from app.services import redactor
from app.services.classifier.hybrid import HybridClassifier
from app.services.prompts import render_analyze_prompt, ANALYZE_SCHEMA, SYSTEM_PROMPT
from app.services.rag import retrieve


async def analyze(session: AsyncSession, req: AnalyzeRequest) -> AnalyzeResponse:
    started = time.perf_counter()
    cfg = settings()

    # 0. Defence in depth. Laravel should have sent redacted text; verify anyway.
    #    A second redaction pass on clean text is a no-op and costs nothing.
    safe = redactor.redact(req.log_excerpt, strict=cfg.redaction_strict)
    excerpt = safe.text

    # 1. Classify (rules → ml → maybe llm)
    basis = req.error_block or excerpt
    classification = HybridClassifier().classify(basis, req.job.failure_reason)

    # 2. Retrieve
    rag_ctx = await retrieve(
        session,
        team_id=req.team_id,
        project_id=None,
        error_message=(req.error_block or excerpt)[:600],
        category=classification.category,
        ecosystem=None,
        job_name=req.job.name,
        signature_hash=req.failure.signature_hash,
    ) if req.use_rag else None

    # 3. Deterministic short-circuit: a known signature with a confirmed fix and a
    #    confident classifier needs no model call at all. This is the cheapest,
    #    fastest and most trustworthy path — take it whenever it is available.
    known = rag_ctx.signature_history if rag_ctx else None
    if known and known.get("is_known") and classification.confidence >= 0.85 and not req.use_llm:
        return _from_known(req, classification, known, rag_ctx, started)

    # 4. LLM
    await assert_within_budget(session, req.team_id)
    provider = build_provider(req.llm_override)

    prompt = render_analyze_prompt(req, classification, rag_ctx, excerpt)

    llm = await provider.complete(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        json_schema=ANALYZE_SCHEMA,
        temperature=cfg.llm_temperature,
        timeout=cfg.llm_timeout_seconds,
    )

    data = llm.parsed
    if not data:
        raise InvalidLLMResponse("empty structured response")

    # 5. Validate and clamp. Never trust a model's self-reported confidence blindly.
    confidence = _calibrate(
        float(data.get("confidence", 0.5)),
        classification=classification,
        rag=rag_ctx,
    )

    return AnalyzeResponse(
        service_version=cfg.service_version,
        category=data.get("category") or classification.category,
        subcategory=data.get("subcategory") or classification.subcategory,
        severity=data.get("severity", "medium"),
        confidence=confidence,
        summary=data["summary"][:500],
        root_cause=data["root_cause"],
        explanation=data.get("explanation"),
        is_transient=bool(data.get("is_transient", False)),
        retry_recommended=bool(data.get("retry_recommended", False)),
        evidence=[Evidence(**e) for e in data.get("evidence", [])][:8],
        recommendations=[Recommendation(**r) for r in data.get("recommendations", [])][:5],
        similar_failures=rag_ctx.similar_failures if rag_ctx else [],
        classification_source=classification.source,
        classification_confidence=classification.confidence,
        used_rag=bool(rag_ctx and rag_ctx.used),
        usage=Usage(
            provider=llm.provider, model=llm.model,
            prompt_tokens=llm.prompt_tokens, completion_tokens=llm.completion_tokens,
            cost_usd=provider.cost(llm.prompt_tokens, llm.completion_tokens),
            latency_ms=int((time.perf_counter() - started) * 1000),
        ),
    )


def _calibrate(raw: float, *, classification, rag) -> float:
    """Adjust the model's stated confidence against independent signals.

    An LLM's self-reported confidence is not calibrated. Corroboration from the
    rule engine and from history is evidence the model does not get to grade itself on.
    """
    score = max(0.0, min(1.0, raw))

    if classification.source == "hybrid" and classification.confidence >= 0.85:
        score = min(0.97, score + 0.05)

    if rag and rag.signature_history and rag.signature_history.get("is_known"):
        score = min(0.98, score + 0.08)

    if rag and not rag.used:
        # No history at all — first time we have seen anything like this.
        score = min(score, 0.85)

    if classification.category == "UNKNOWN":
        score = min(score, 0.70)

    return round(score, 3)
```

```python
# ready — app/core/budget.py
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BudgetExceeded


async def assert_within_budget(session: AsyncSession, team_id: int) -> None:
    """Hard stop before spending. Checked on every LLM call, not sampled."""
    row = await session.execute(text("""
        SELECT
            COALESCE(SUM(ar.cost_usd), 0) AS spent,
            (SELECT monthly_ai_budget_usd FROM teams WHERE id = :tid) AS budget
        FROM ai_requests ar
        WHERE ar.team_id = :tid
          AND ar.created_at >= date_trunc('month', now())
    """), {"tid": team_id})

    spent, budget = row.one()

    if budget and float(spent) >= float(budget):
        raise BudgetExceeded(
            f"Monthly AI budget reached (${spent:.2f} of ${budget:.2f}). "
            f"Raise it in workspace settings or switch to a local provider."
        )
```

> **The short-circuit in step 3 is the most valuable optimization in the system.** A team that hits the same misconfigured healthcheck every week gets an instant, free, perfectly accurate answer from the fourth occurrence onward. Track how often it fires — it is the clearest evidence that historical intelligence works.

- [ ] `analyzer.py` implemented
- [ ] `/v1/analyze` returns a valid `AnalyzeResponse` for all five fixtures
- [ ] Budget enforcement tested (set budget to 0, expect 402)

---

## 9.7 Recommendations

Generated inside the analysis call, then validated against a whitelist.

```python
# ready — app/services/recommender.py
ACTION_RISK: dict[str, str] = {
    "investigate":         "low",
    "retry_job":           "low",
    "retry_pipeline":      "low",
    "create_issue":        "low",
    "edit_file":           "medium",
    "update_dependency":   "medium",
    "create_merge_request":"medium",
    "update_config":       "high",
    "rollback_deployment": "critical",
    "manual":              "medium",
}


def sanitize(recommendations: list[dict], *, is_default_branch: bool) -> list[dict]:
    """The model proposes; this function constrains. Never ship a model's risk rating."""
    out = []

    for r in recommendations:
        action = r.get("action_type", "manual")
        if action not in ACTION_RISK:
            action = "manual"

        # Risk is assigned by us from the action type. A model claiming
        # "rollback_deployment, risk: low" must not be able to lower the gate.
        risk = ACTION_RISK[action]

        # Anything touching the default branch escalates one level.
        if is_default_branch and risk in ("medium", "high"):
            risk = {"medium": "high", "high": "critical"}[risk]

        r["action_type"] = action
        r["risk"] = risk
        out.append(r)

    return out[:5]
```

> **Never let the model set its own risk level.** Risk determines whether the policy engine (file 18) executes something automatically. A model that can label a production rollback "low risk" can talk its way past your safety layer. Risk is a property of the action type, assigned by code.

- [ ] `recommender.py` implemented, called on every analysis
- [ ] Test: a model claiming `rollback_deployment / low` comes back `critical`

---

## Definition of Done

```bash
# providers
pytest tests/unit/test_providers.py -v
curl -s -H "X-PipeMind-Token: $SERVICE_TOKEN" localhost:8001/v1/info | jq '.providers'

# embeddings + similarity
curl -s -X POST localhost:8001/v1/embed \
  -H "X-PipeMind-Token: $SERVICE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"SQLSTATE[HY000] [2002] Connection refused"}' | jq '.dimensions'   # 384

# full analysis on a real fixture
curl -s -X POST localhost:8001/v1/analyze \
  -H "X-PipeMind-Token: $SERVICE_TOKEN" -H 'Content-Type: application/json' \
  -d @tests/fixtures/analyze-request-db.json | jq '{
     category, subcategory, severity, confidence, summary, root_cause,
     classification_source, used_rag,
     evidence: (.evidence | length),
     recommendations: (.recommendations | length),
     cost: .usage.cost_usd, latency: .usage.latency_ms
   }'

# the short-circuit fires on a repeat
# (run the same analysis twice after marking the signature known — second call
#  must return with used_rag=true and cost_usd=0)
```

Targets for M3:

| Metric | Target |
|---|---|
| Analysis latency p50 | < 6 s |
| Cost per analysis | < $0.01 |
| Evidence items with a valid `source_ref` | 100% |
| Invalid JSON from a schema-constrained provider | 0 |
| Root-cause judged correct by you on the 5 fixtures | 5/5 |

- [ ] All five fixtures produce a correct root cause
- [ ] Every evidence item cites something that exists in the input
- [ ] Budget ceiling enforced
- [ ] Prompt version recorded in `PipeMind-data/experiments/prompt-v1.md`

**Next:** [`10-backend-ai-integration.md`](10-backend-ai-integration.md)
