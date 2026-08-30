# 06 — AI Service Setup

**Repo:** `PipeMind-ai` · **Depends on:** 05 · **Milestone:** M3

The Python intelligence service: FastAPI skeleton, pinned dependencies, config, DB access, auth against Laravel, Docker, and the **versioned contract** both sides code against.

> The AI service owns no application state. It reads from Postgres for similarity and knowledge; it writes nothing except embeddings. Laravel remains the source of truth.

---

## 6.1 Project scaffold

```bash
# ready
cd PipeMind-ai
mkdir -p app/{api,models,services/classifier,providers,db,prompts,core} \
         models scripts tests/{unit,integration,fixtures}
touch app/__init__.py app/api/__init__.py app/models/__init__.py \
      app/services/__init__.py app/services/classifier/__init__.py \
      app/providers/__init__.py app/db/__init__.py app/core/__init__.py \
      models/.gitkeep
```

```text
PipeMind-ai/
├── app/
│   ├── main.py                 FastAPI app, lifespan, middleware
│   ├── config.py               pydantic-settings
│   ├── deps.py                 DI: db session, auth, provider resolution
│   ├── api/
│   │   ├── router.py           mounts everything under /v1
│   │   ├── health.py           GET /health, GET /v1/info
│   │   ├── logs.py             POST /v1/logs/process
│   │   ├── classify.py         POST /v1/classify
│   │   ├── embed.py            POST /v1/embed
│   │   ├── similar.py          POST /v1/similar
│   │   ├── analyze.py          POST /v1/analyze          ← the main one
│   │   └── recommend.py        POST /v1/recommend
│   ├── models/
│   │   ├── requests.py         pydantic request schemas
│   │   ├── responses.py        pydantic response schemas
│   │   └── domain.py           internal value objects
│   ├── services/
│   │   ├── redactor.py         file 07
│   │   ├── log_processor.py    file 07
│   │   ├── signature.py        file 07
│   │   ├── classifier/         file 08
│   │   ├── embeddings.py       file 09
│   │   ├── similarity.py       file 09
│   │   ├── rag.py              file 09
│   │   ├── analyzer.py         file 09  — orchestrates the pipeline
│   │   └── recommender.py      file 09
│   ├── providers/
│   │   ├── base.py             LLMProvider protocol
│   │   ├── gemini.py
│   │   ├── ollama.py
│   │   ├── openai_compatible.py
│   │   └── registry.py
│   ├── db/
│   │   ├── session.py          async SQLAlchemy engine
│   │   └── queries.py          read-only queries + embedding writes
│   ├── prompts/
│   │   ├── analyze.j2
│   │   ├── classify.j2
│   │   └── recommend.j2
│   └── core/
│       ├── errors.py           typed exceptions → HTTP codes
│       ├── logging.py          structlog, JSON output
│       ├── security.py         shared-secret auth
│       └── budget.py           cost ceiling enforcement
├── models/                     trained artifacts (gitignored)
├── scripts/                    dataset.py train.py evaluate.py benchmark.py
├── tests/
├── Dockerfile
├── pyproject.toml
└── README.md
```

- [ ] Scaffold created

---

## 6.2 Dependencies

`uv` for speed and a real lockfile.

```bash
# ready
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.11
source .venv/bin/activate
```

```toml
# ready — pyproject.toml
[project]
name = "pipemind-ai"
version = "0.1.0"
description = "PipeMind intelligence layer — CI/CD failure analysis"
requires-python = ">=3.11,<3.13"

dependencies = [
    # web
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.32,<1.0",
    "pydantic>=2.9,<3.0",
    "pydantic-settings>=2.6,<3.0",
    "orjson>=3.10,<4.0",
    "python-multipart>=0.0.12",

    # http + resilience
    "httpx>=0.27,<1.0",
    "tenacity>=9.0,<10.0",

    # data
    "sqlalchemy[asyncio]>=2.0.36,<3.0",
    "psycopg[binary,pool]>=3.2,<4.0",
    "pgvector>=0.3.6,<0.4",
    "redis>=5.2,<6.0",

    # ml / nlp
    "numpy>=1.26,<3.0",
    "pandas>=2.2,<3.0",
    "scikit-learn>=1.5,<2.0",
    "scipy>=1.14,<2.0",
    "joblib>=1.4,<2.0",
    "sentence-transformers>=3.3,<4.0",

    # llm providers
    "google-genai>=0.8,<2.0",
    "openai>=1.57,<2.0",          # also covers Ollama's OpenAI-compatible endpoint

    # templating + observability
    "jinja2>=3.1,<4.0",
    "structlog>=24.4,<26.0",
    "prometheus-client>=0.21,<1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9.0",
    "pytest-asyncio>=0.24,<1.0",
    "pytest-cov>=6.0,<7.0",
    "ruff>=0.8,<1.0",
    "mypy>=1.13,<2.0",
    "types-requests",
    "respx>=0.21,<1.0",           # httpx mocking
    "faker>=33.0,<40.0",
    "matplotlib>=3.9,<4.0",       # evaluation plots for the report
    "seaborn>=0.13,<1.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E","F","I","N","UP","B","SIM","RUF"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

```bash
# ready — CPU-only torch keeps the image ~2 GB instead of ~7 GB
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -e ".[dev]"
uv lock
```

- [ ] `uv.lock` committed
- [ ] `python -c "import torch, sentence_transformers, sklearn; print('ok')"` passes

> **Pin `torch` to the CPU wheel deliberately.** The default wheel drags in CUDA and turns a 2 GB image into 7 GB for zero benefit on a machine without a GPU. If you later move embeddings to a GPU box, change the index URL there — not in the default build.

---

## 6.3 Config

```python
# ready — app/config.py
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8001
    service_version: str = "0.1.0"
    contract_version: str = "v1"

    # must equal AI_SERVICE_TOKEN in Laravel
    service_token: str

    database_url: str
    redis_url: str = "redis://localhost:6379/3"

    # llm
    llm_provider: Literal["gemini", "ollama", "openai_compatible"] = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    llm_timeout_seconds: int = 90
    llm_max_retries: int = 2
    llm_temperature: float = 0.2
    max_context_tokens: int = 8000

    # embeddings
    embedding_provider: Literal["local", "gemini"] = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    embedding_batch_size: int = 32

    # log processing
    max_log_chars: int = 60_000
    excerpt_context_lines: int = 15
    redaction_strict: bool = True

    # retrieval
    similarity_threshold: float = 0.75
    max_similar_failures: int = 5
    max_knowledge_chunks: int = 4

    # cost
    monthly_cost_ceiling_usd: float = 25.0


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] `app/config.py` written, `.env` present from file 01

---

## 6.4 Auth, errors, logging

```python
# ready — app/core/security.py
import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_service_token(
    x_pipemind_token: str = Header(default=""),
) -> None:
    """Constant-time shared-secret check.

    This service is never exposed publicly. It sits on the internal network and
    trusts exactly one caller: Laravel. There are no user identities here.
    """
    expected = settings().service_token

    if not expected or not hmac.compare_digest(x_pipemind_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid service token")
```

```python
# ready — app/core/errors.py
class PipeMindAIError(Exception):
    code = "AI_ERROR"
    status = 500
    retryable = False


class LLMUnavailable(PipeMindAIError):
    code, status, retryable = "AI_PROVIDER_ERROR", 503, True


class LLMTimeout(PipeMindAIError):
    code, status, retryable = "AI_PROVIDER_TIMEOUT", 504, True


class LLMRateLimited(PipeMindAIError):
    code, status, retryable = "AI_PROVIDER_RATE_LIMITED", 429, True


class InvalidLLMResponse(PipeMindAIError):
    """Model returned something we could not parse into the contract."""
    code, status, retryable = "AI_INVALID_RESPONSE", 502, True


class BudgetExceeded(PipeMindAIError):
    code, status, retryable = "AI_BUDGET_EXCEEDED", 402, False


class RedactionFailed(PipeMindAIError):
    """Fail closed: if redaction cannot complete, nothing leaves the building."""
    code, status, retryable = "AI_REDACTION_FAILED", 500, False
```

> `RedactionFailed` is `retryable = False` on purpose. A retry loop around a redaction bug is a loop that keeps trying to ship secrets to a third party. It must stop and stay stopped.

```python
# ready — app/core/logging.py
import logging
import sys

import structlog

from app.config import settings


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=settings().log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings().log_level)
        ),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger("pipemind.ai")
```

**Never log:** raw log content, prompt bodies, API keys, or anything from `credentials`. Log identifiers, counts, timings and outcomes. A log line that helps you debug should not itself become the leak.

- [ ] `security.py`, `errors.py`, `logging.py` written

---

## 6.5 Database access

Read-only, except embeddings.

```python
# ready — app/db/session.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings().database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

```python
# ready — app/db/queries.py  (raw SQL: we read Laravel's schema, we don't own it)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def find_similar_failures(
    session: AsyncSession,
    team_id: int,
    embedding: list[float],
    limit: int = 5,
    threshold: float = 0.75,
    exclude_failure_id: int | None = None,
) -> list[dict]:
    """Cosine similarity over pgvector, resolved failures preferred.

    `<=>` is cosine distance, so similarity = 1 - distance.
    """
    sql = text("""
        SELECT
            f.id, f.uuid::text AS uuid, f.category, f.subcategory,
            f.error_message, f.failed_at, f.resolved_at, f.resolution_type,
            f.resolution_note, f.time_to_resolution_seconds,
            p.name AS project_name,
            s.known_root_cause, s.known_resolution, s.is_known,
            1 - (fe.embedding <=> CAST(:emb AS vector)) AS similarity
        FROM failure_embeddings fe
        JOIN failures f  ON f.id = fe.failure_id
        JOIN projects  p ON p.id = f.project_id
        LEFT JOIN failure_signatures s ON s.id = f.signature_id
        WHERE fe.team_id = :team_id
          AND (:exclude IS NULL OR f.id <> :exclude)
          AND 1 - (fe.embedding <=> CAST(:emb AS vector)) >= :threshold
        ORDER BY
            -- a resolved neighbour is worth more than a marginally closer unresolved one
            (f.resolved_at IS NOT NULL) DESC,
            fe.embedding <=> CAST(:emb AS vector)
        LIMIT :limit
    """)

    rows = await session.execute(sql, {
        "team_id": team_id,
        "emb": str(embedding),
        "limit": limit,
        "threshold": threshold,
        "exclude": exclude_failure_id,
    })

    return [dict(r) for r in rows.mappings()]
```

> **Order by resolution first, distance second.** A 0.94-similar failure nobody ever fixed teaches the model nothing. A 0.88-similar failure with a confirmed resolution is the entire point of having history. Retrieval quality here is not raw closeness — it is *usefulness*.

Other queries to implement: `find_knowledge_chunks`, `get_project_context`, `get_signature_history`, `get_job_baseline`, `insert_failure_embedding`, `month_to_date_cost`.

- [ ] `session.py` + `queries.py` written
- [ ] `SELECT 1` against the live DB succeeds from the service

---

## 6.6 The contract

Freeze this in `PipeMind-data/contracts/v1/` **before** writing either side. Both repos import from it conceptually; drift between them is the failure mode this prevents.

```python
# ready — app/models/requests.py
from pydantic import BaseModel, Field


class ChangedFile(BaseModel):
    path: str
    change_type: str
    additions: int = 0
    deletions: int = 0
    is_config: bool = False
    is_dependency: bool = False


class ProjectContext(BaseModel):
    uuid: str
    name: str
    tech_stack: list[str] = Field(default_factory=list)
    provider: str
    default_branch: str = "main"


class PipelineContext(BaseModel):
    iid: int | None = None
    ref: str
    source: str = "push"
    commit_sha: str | None = None
    commit_message: str | None = None
    duration_seconds: int | None = None
    previous_status: str | None = None      # status of the previous pipeline on this ref
    changed_files: list[ChangedFile] = Field(default_factory=list)


class JobContext(BaseModel):
    name: str
    stage_name: str
    status: str
    exit_code: int | None = None
    duration_seconds: int | None = None
    failure_reason: str | None = None
    baseline_duration_seconds: float | None = None


class FailureContext(BaseModel):
    uuid: str
    occurrence_index: int = 1
    is_flaky: bool = False
    signature_hash: str | None = None


class AnalyzeRequest(BaseModel):
    contract_version: str = "v1"
    team_id: int
    failure: FailureContext
    project: ProjectContext
    pipeline: PipelineContext
    job: JobContext

    # already redacted by /v1/logs/process — but the analyzer re-checks anyway
    log_excerpt: str
    error_block: str | None = None
    stack_trace: str | None = None

    use_rag: bool = True
    use_llm: bool = True
    llm_override: dict | None = None        # provider/model/api_key from the team's ai_providers row
```

```python
# ready — app/models/responses.py
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    type: str                     # log_line | changed_file | historical_failure | metric | config
    content: str
    source_ref: str | None = None
    line_number: int | None = None
    related_failure_uuid: str | None = None
    weight: float = Field(0.5, ge=0, le=1)


class Recommendation(BaseModel):
    title: str
    description: str
    rationale: str | None = None
    action_type: str
    risk: str = "medium"
    confidence: float = Field(0.5, ge=0, le=1)
    affected_files: list[str] = Field(default_factory=list)
    patch: str | None = None


class SimilarFailure(BaseModel):
    uuid: str
    similarity: float
    project_name: str
    occurred_at: str
    root_cause: str | None = None
    resolution: str | None = None
    resolved: bool = False


class Usage(BaseModel):
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False


class AnalyzeResponse(BaseModel):
    contract_version: str = "v1"
    service_version: str

    category: str
    subcategory: str | None = None
    severity: str
    confidence: float = Field(ge=0, le=1)

    summary: str
    root_cause: str
    explanation: str | None = None

    is_transient: bool = False
    retry_recommended: bool = False

    evidence: list[Evidence] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    similar_failures: list[SimilarFailure] = Field(default_factory=list)

    classification_source: str            # rules | ml | llm | hybrid
    classification_confidence: float
    used_rag: bool = False

    usage: Usage
```

### Endpoint table

| Method | Path | Purpose | Called by |
|---|---|---|---|
| GET | `/health` | liveness, no auth | uptime checks |
| GET | `/v1/info` | version, contract, loaded models, provider status | Laravel `/system/status` |
| POST | `/v1/logs/process` | redact → clean → extract → signature | `ProcessJobLog` |
| POST | `/v1/classify` | category only, no LLM by default | `ProcessJobLog`, batch scripts |
| POST | `/v1/embed` | text → vector | `EmbedFailure` |
| POST | `/v1/similar` | vector → nearest historical failures | `/failures/{f}/similar` |
| POST | `/v1/analyze` | **the full pipeline** | `AnalyzeFailure` |
| POST | `/v1/recommend` | recommendations for an existing analysis | re-generation |

All `/v1/*` require `X-PipeMind-Token`.

- [ ] Request/response models written
- [ ] Copy the JSON Schema into `PipeMind-data/contracts/v1/` (`analyze.request.json`, `analyze.response.json`, …) via `AnalyzeRequest.model_json_schema()`
- [ ] `contracts/v1/CHANGELOG.md` created — every change to a shape gets an entry

> **Versioning rule:** additive changes (a new optional field) stay in `v1`. Anything that removes a field, renames one, or changes a type creates `v2`, and both run side by side until Laravel migrates. `contract_version` travels in every request and response so a mismatch is a loud error, not a silent wrong answer.

---

## 6.7 App entrypoint

```python
# ready — app/main.py
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import ORJSONResponse

from app.api.router import router
from app.config import settings
from app.core.errors import PipeMindAIError
from app.core.logging import configure_logging, log
from app.core.security import require_service_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()

    # Warm the embedding model at boot. Lazy-loading it costs ~8 s on the first
    # request, which lands squarely on a user waiting for their first analysis.
    from app.services.embeddings import get_embedder
    get_embedder()

    from app.services.classifier.rules import RuleClassifier
    RuleClassifier.warm()

    log.info("ai.started", version=settings().service_version,
             provider=settings().llm_provider, embedding=settings().embedding_model)
    yield
    log.info("ai.stopped")


app = FastAPI(
    title="PipeMind AI",
    version=settings().service_version,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/docs" if settings().app_env == "local" else None,
)

app.include_router(router, prefix="/v1", dependencies=[Depends(require_service_token)])


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "version": settings().service_version}


@app.exception_handler(PipeMindAIError)
async def handle_domain_error(_, exc: PipeMindAIError):
    log.warning("ai.error", code=exc.code, message=str(exc))

    return ORJSONResponse(
        status_code=exc.status,
        content={"message": str(exc), "error_code": exc.code, "retryable": exc.retryable},
    )
```

The error body deliberately mirrors Laravel's shape from file 04 — Laravel can forward it to the frontend unchanged.

- [ ] `main.py` written, `uvicorn app.main:app --reload --port 8001` boots
- [ ] `curl localhost:8001/health` → `{"status":"ok",…}`
- [ ] `curl -H 'X-PipeMind-Token: …' localhost:8001/v1/info` → version + provider status

---

## 6.8 Docker

```dockerfile
# ready — Dockerfile
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/.hf

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN uv pip install --system torch --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --system -r pyproject.toml

# Bake the embedding model into the image. Downloading it at container start
# makes cold boots slow and ties startup to Hugging Face being reachable.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app ./app
COPY models ./models
COPY scripts ./scripts

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8001/health || exit 1

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8001","--workers","2"]
```

```yaml
# ready — append to PipeMind-back/docker-compose.yml
  ai:
    build: ../PipeMind-ai
    container_name: pipemind-ai
    restart: unless-stopped
    env_file: ../PipeMind-ai/.env
    environment:
      DATABASE_URL: postgresql+psycopg://pipemind:secret@postgres:5432/pipemind
      REDIS_URL: redis://redis:6379/3
    ports:
      - "8001:8001"
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    volumes:
      - ../PipeMind-ai/models:/srv/models
      - hfcache:/models/.hf
    networks: [pipemind]

volumes:
  hfcache:
```

- [ ] Image builds, `docker compose up ai` healthy
- [ ] Image size under 2.5 GB (`docker images pipemind-ai`)

---

## 6.9 Provider strategy — cloud and local, both

PipeMind supports **two independent provider choices**. Conflating them is the most common mistake here, so state it plainly:

| Choice | Options | Needs an API key? | Runs where? |
|---|---|---|---|
| **LLM** (reasoning, root cause) | Gemini · OpenAI-compatible · Ollama | Cloud: yes · Ollama: no | Cloud API or your machine |
| **Embeddings** (similarity, RAG) | `all-MiniLM-L6-v2` **local** · Gemini | Local: **no** | CPU, ~90 MB, bundled in the image |

**The default configuration is already hybrid:** Gemini for reasoning, a local model for embeddings. Embeddings do not need a GPU, a key, or the internet — a 384-dim MiniLM runs in single-digit milliseconds on any laptop CPU, and it keeps your similarity search free and instant regardless of which LLM you pick.

This is why `EMBEDDING_DIM=384` in the schema (file 02) is the right call **whatever you decide about the LLM**. The embedding choice is independent, already local, and already free.

### What works with no API key at all

You do not need a key to start. Everything below is fully buildable today:

| File | Needs a key? |
|---|---|
| 06 service setup · 07 log processing + redaction | No |
| 08 classification (rules + ML) | No |
| 09 embeddings · similarity · RAG retrieval | No |
| 09 LLM reasoning | **Yes** — or use the stub below |
| 10 backend integration | Stub is enough to build against |
| 11–16 the entire frontend | No |

Files 07, 08 and the retrieval half of 09 are pure Python — regex, scikit-learn and sentence-transformers. The classifier alone already produces a category and confidence for most failures.

### The stub provider — build the whole pipeline before the key arrives

```python
# ready — app/providers/stub.py
import json
import time

from app.providers.base import LLMResponse
from app.services.classifier.hybrid import HybridClassifier


class StubProvider:
    """Deterministic fake LLM for development, tests and CI.

    Produces a well-formed AnalyzeResponse derived from the rule classifier, so
    the entire pipeline — persistence, caching, the frontend, the E2E suite —
    can be built and tested with no key, no network and no cost.

    Never enabled outside local/testing: main.py refuses to register it otherwise.
    """

    name = "stub"

    def __init__(self, model: str = "stub-v1") -> None:
        self._model = model

    async def complete(self, *, system: str, prompt: str, json_schema=None,
                       temperature: float = 0.2, max_tokens: int = 4096,
                       timeout: int = 90) -> LLMResponse:
        started = time.perf_counter()

        # Classify from the prompt body so the output tracks the real input
        # rather than being a fixed blob — the frontend then exercises every
        # category, severity and confidence path.
        c = HybridClassifier().classify(prompt)

        payload = {
            "category": c.category,
            "subcategory": c.subcategory,
            "severity": "high" if c.confidence > 0.8 else "medium",
            "confidence": round(min(0.93, max(0.45, c.confidence)), 3),
            "summary": f"Stubbed analysis: {c.category} failure detected.",
            "root_cause": (
                f"[STUB — no LLM configured] The rule classifier matched "
                f"{', '.join(c.matched_rules) or 'no specific pattern'}. "
                f"Configure an AI provider to get a real root-cause analysis."
            ),
            "explanation": None,
            "is_transient": c.category in ("NETWORK", "INFRASTRUCTURE"),
            "retry_recommended": c.category in ("NETWORK", "INFRASTRUCTURE"),
            "evidence": [
                {"type": "log_line", "content": "Matched by the rule classifier",
                 "source_ref": "classifier", "weight": c.confidence},
            ],
            "recommendations": [
                {"title": "Configure an AI provider for real analysis",
                 "description": "Add a Gemini key or a local Ollama model in workspace settings.",
                 "action_type": "investigate", "risk": "low", "confidence": 1.0,
                 "affected_files": []},
            ],
        }

        return LLMResponse(
            text=json.dumps(payload),
            parsed=payload,
            prompt_tokens=len(prompt) // 4,
            completion_tokens=180,
            model=self._model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def health(self) -> bool:
        return True

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0
```

```python
# ready — app/providers/registry.py, guard at the top of build_provider()
if kind == "stub":
    if settings().app_env not in ("local", "testing"):
        raise LLMUnavailable("The stub provider is not permitted outside local/testing.")
    return StubProvider()
```

> **The stub is labelled in its own output.** `[STUB — no LLM configured]` appears in the root cause, so nobody — including you, three weeks from now — mistakes a stubbed analysis for a real one in a screenshot or a demo. A silent fake is worse than no fake.

```bash
# .env while you wait for the key
LLM_PROVIDER=stub
EMBEDDING_PROVIDER=local      # already works, no key needed
```

### Switching to Gemini when the key arrives

One env var locally, or one row in `ai_providers` per team in the app:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your key>
GEMINI_MODEL=gemini-2.0-flash
```

Nothing else changes. No migration, no refactor, no frontend change — that is the entire point of the `LLMProvider` abstraction in file 09.

Verify current model names and per-token pricing from Google's docs when you add it, and put the rates into the `ai_providers` row (`input_cost_per_1k` / `output_cost_per_1k`). Do not hardcode them.

### Adding local later

```yaml
# ready — PipeMind-back/docker-compose.ollama.yml   (start only when you want it)
name: pipemind-ollama
services:
  ollama:
    image: ollama/ollama:latest
    container_name: pipemind-ollama
    restart: unless-stopped
    ports: ["11434:11434"]
    volumes: [ollamadata:/root/.ollama]
    networks: [pipemind]
volumes:
  ollamadata:
networks:
  pipemind: { external: true }
```

```bash
# ready — pick by what your machine has
docker exec pipemind-ollama ollama pull qwen2.5-coder:7b   # ~4.7 GB · needs ~8 GB RAM
docker exec pipemind-ollama ollama pull qwen2.5-coder:3b   # ~2 GB   · needs ~4 GB RAM
docker exec pipemind-ollama ollama pull llama3.2:3b        # ~2 GB   · general purpose
```

Hardware reality, so you can plan rather than discover:

| Model | RAM | CPU-only speed | Quality vs Gemini Flash |
|---|---|---|---|
| `qwen2.5-coder:3b` | ~4 GB | ~30–60 s / analysis | Noticeably weaker |
| `qwen2.5-coder:7b` | ~8 GB | ~60–120 s / analysis | Weaker but usable |
| `qwen2.5-coder:7b` on 8 GB VRAM | GPU | ~5–10 s | Weaker but usable |

> A 7B local model produces meaningfully weaker root-cause reasoning than a frontier cloud model, and its JSON is a hint rather than a constraint (see `salvage_json` in file 09). Its value is privacy and zero marginal cost, not quality. **Measure both in file 23** — a table comparing Gemini and Ollama on the same 30 failures is one of the strongest results in your report, precisely because it reports a real trade-off instead of asserting a winner.

- [ ] `StubProvider` implemented with the env guard
- [ ] `LLM_PROVIDER=stub` gets you through files 07–16 with no key
- [ ] Gemini row added to `ai_providers` when the key arrives, with current pricing
- [ ] Ollama documented as available; pull a model only when you have the RAM

---

## Definition of Done

```bash
# service
uvicorn app.main:app --port 8001 &
curl -s localhost:8001/health | jq .
curl -s -H "X-PipeMind-Token: $SERVICE_TOKEN" localhost:8001/v1/info | jq .

# auth actually enforced
curl -s -o /dev/null -w "%{http_code}\n" localhost:8001/v1/info          # 401
curl -s -o /dev/null -w "%{http_code}\n" -H "X-PipeMind-Token: wrong" \
     localhost:8001/v1/info                                              # 401

# db reachable from the service
python -c "
import asyncio
from sqlalchemy import text
from app.db.session import SessionLocal
async def go():
    async with SessionLocal() as s:
        print((await s.execute(text('select count(*) from projects'))).scalar())
asyncio.run(go())
"

# Laravel can reach it
docker exec pipemind-back curl -fsS http://ai:8001/health
```

- [ ] All checks pass
- [ ] Contract JSON schemas committed in `PipeMind-data/contracts/v1/`
- [ ] `ruff check .` and `mypy app` clean

**Next:** [`07-ai-log-processing.md`](07-ai-log-processing.md)
