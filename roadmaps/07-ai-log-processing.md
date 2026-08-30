# 07 — Log Processing & Redaction

**Repo:** `PipeMind-ai` · **Depends on:** 06 · **Milestone:** M3

Turn a 48,000-line CI log into ~40 relevant lines, with every secret removed first. This file is the one that makes PipeMind safe to point at a real company's pipelines.

**Order is non-negotiable: redact → clean → extract → signature.** Redaction runs first because every later stage copies text around, and a secret that survives stage one will be in four places by stage four.

---

## 7.1 Secret redaction

```python
# ready — app/services/redactor.py
import math
import re
from dataclasses import dataclass, field
from typing import Pattern

from app.core.errors import RedactionFailed


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: Pattern[str]
    replacement: str
    # group index to keep (e.g. keep the key name, redact the value)
    keep_group: int | None = None


def _c(p: str) -> Pattern[str]:
    return re.compile(p, re.IGNORECASE | re.MULTILINE)


RULES: list[Rule] = [
    # ---- cloud provider keys (highest value, most specific) ----
    Rule("aws_access_key",  _c(r"\b(AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    Rule("aws_secret",      _c(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
                            "[REDACTED_AWS_SECRET]"),
    Rule("gcp_key",         _c(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[REDACTED_GCP_KEY]"),
    Rule("gcp_service_acct",_c(r'"private_key"\s*:\s*"-----BEGIN[^"]+"'),
                            '"private_key": "[REDACTED_PRIVATE_KEY]"'),
    Rule("azure_secret",    _c(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                               r"\s*[:=]\s*\S{20,}"), "[REDACTED_AZURE_SECRET]"),

    # ---- vcs / registry / ci tokens ----
    Rule("github_token",    _c(r"\b(gh[pousr]_[A-Za-z0-9]{36,255})\b"), "[REDACTED_GITHUB_TOKEN]"),
    Rule("github_fine",     _c(r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b"), "[REDACTED_GITHUB_PAT]"),
    Rule("gitlab_token",    _c(r"\b(glpat|glptt|gldt|glrt|glsoat|glimt|glagent)-[A-Za-z0-9_\-]{20,}\b"),
                            "[REDACTED_GITLAB_TOKEN]"),
    Rule("slack_token",     _c(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    Rule("slack_webhook",   _c(r"https://hooks\.slack\.com/services/\S+"), "[REDACTED_SLACK_WEBHOOK]"),
    Rule("npm_token",       _c(r"\bnpm_[A-Za-z0-9]{36}\b"), "[REDACTED_NPM_TOKEN]"),
    Rule("pypi_token",      _c(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}\b"), "[REDACTED_PYPI_TOKEN]"),
    Rule("docker_auth",     _c(r'"auth"\s*:\s*"[A-Za-z0-9+/=]{20,}"'), '"auth": "[REDACTED]"'),
    Rule("stripe_key",      _c(r"\b(sk|rk|pk)_(live|test)_[A-Za-z0-9]{20,}\b"), "[REDACTED_STRIPE_KEY]"),
    Rule("openai_key",      _c(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED_API_KEY]"),
    Rule("anthropic_key",   _c(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED_API_KEY]"),

    # ---- generic bearer / basic / jwt ----
    Rule("jwt",             _c(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
                            "[REDACTED_JWT]"),
    Rule("bearer",          _c(r"(Bearer|Token|Authorization:)\s+\S{12,}"), r"\1 [REDACTED]", keep_group=1),
    Rule("basic_auth_url",  _c(r"://([^:/\s]+):([^@/\s]+)@"), "://[REDACTED]:[REDACTED]@"),

    # ---- env-var assignments (the single most common leak in CI logs) ----
    Rule("env_secret",      _c(r"\b([A-Z0-9_]*(PASSWORD|PASSWD|SECRET|TOKEN|APIKEY|API_KEY|"
                               r"PRIVATE_KEY|ACCESS_KEY|CREDENTIAL|AUTH|SIGNING_KEY|"
                               r"ENCRYPTION_KEY|DSN)[A-Z0-9_]*)\s*[:=]\s*['\"]?([^\s'\"]+)"),
                            r"\1=[REDACTED]", keep_group=1),

    # ---- connection strings ----
    Rule("db_url",          _c(r"\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)"
                               r"://[^:\s]+:[^@\s]+@[^\s]+"), r"\1://[REDACTED_CONNECTION_STRING]"),

    # ---- keys & certs ----
    Rule("private_key",     _c(r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]+?-----END[A-Z ]*PRIVATE KEY-----"),
                            "[REDACTED_PRIVATE_KEY_BLOCK]"),
    Rule("ssh_key",         _c(r"\bssh-(rsa|ed25519|dss)\s+[A-Za-z0-9+/=]{40,}"), "[REDACTED_SSH_KEY]"),

    # ---- PII ----
    Rule("email",           _c(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
                            "[REDACTED_EMAIL]"),
]

# Emails inside commit metadata are legitimate signal, and these hosts are not secrets.
EMAIL_ALLOWLIST = re.compile(
    r"@(users\.noreply\.github\.com|noreply\.gitlab\.com|example\.(com|org))$", re.I
)


@dataclass
class RedactionResult:
    text: str
    count: int = 0
    types: list[str] = field(default_factory=list)


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {c: s.count(c) for c in set(s)}
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


HIGH_ENTROPY_CANDIDATE = re.compile(r"(?<![A-Za-z0-9+/=_\-])[A-Za-z0-9+/=_\-]{32,128}(?![A-Za-z0-9+/=_\-])")

# Things that look random but are not secrets. Redacting these destroys the signal
# we actually need — a commit SHA is often the most useful token in the whole log.
ENTROPY_EXCLUDE = re.compile(
    r"^(?:"
    r"[0-9a-f]{7,40}"                      # git SHAs
    r"|sha256:[0-9a-f]{64}"                # image digests
    r"|[0-9a-f]{32}"                       # md5 / cache keys
    r"|[A-Za-z0-9_\-]+\.(js|ts|css|map|so|jar|whl|tar|gz)"   # hashed asset filenames
    r")$",
    re.I,
)


def redact(text: str, *, strict: bool = True) -> RedactionResult:
    """Remove secrets. Fail closed — never return partially-redacted text on error."""
    if not text:
        return RedactionResult(text="", count=0, types=[])

    try:
        found: dict[str, int] = {}
        out = text

        for rule in RULES:
            if rule.name == "email":
                def _email(m: re.Match[str]) -> str:
                    if EMAIL_ALLOWLIST.search(m.group(0)):
                        return m.group(0)
                    found["email"] = found.get("email", 0) + 1
                    return rule.replacement

                out = rule.pattern.sub(_email, out)
                continue

            out, n = rule.pattern.subn(rule.replacement, out)
            if n:
                found[rule.name] = found.get(rule.name, 0) + n

        if strict:
            def _entropy(m: re.Match[str]) -> str:
                tok = m.group(0)
                if ENTROPY_EXCLUDE.match(tok):
                    return tok
                if _shannon_entropy(tok) >= 4.2:
                    found["high_entropy"] = found.get("high_entropy", 0) + 1
                    return "[REDACTED_HIGH_ENTROPY]"
                return tok

            out = HIGH_ENTROPY_CANDIDATE.sub(_entropy, out)

        return RedactionResult(text=out, count=sum(found.values()), types=sorted(found))

    except Exception as exc:  # noqa: BLE001
        raise RedactionFailed(f"redaction aborted: {type(exc).__name__}") from exc
```

**Rules for maintaining this module:**

1. **Order matters.** Specific patterns (`AKIA…`) run before generic ones (40-char base64), or the generic rule eats the specific match and you lose the type label.
2. **Entropy detection is a net, not a scalpel.** 4.2 bits/char catches most base64 secrets while leaving prose and SHAs alone. Tune it against real logs, and always with the exclusion list.
3. **Every new rule needs a test with a real-shaped example** and a negative test proving it does not eat legitimate content.
4. **Fail closed.** Any exception aborts the whole call. Never return "mostly redacted".
5. **`strict=False` exists only for local models** where the text never leaves your infrastructure — and even then, redaction still runs, just without the entropy net.

- [ ] `redactor.py` written
- [ ] ≥ 25 unit tests, one per rule plus negatives
- [ ] A test asserting a commit SHA and an image digest survive entropy redaction

---

## 7.2 Log cleaning

```python
# ready — app/services/log_processor.py  (cleaning half)
import re

ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
GITLAB_SECTION = re.compile(r"section_(start|end):\d+:\S+\r?", re.M)
GITHUB_CMD = re.compile(r"^##\[(group|endgroup|command|section|debug)\].*$", re.M)
TIMESTAMP_PREFIX = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\s*)"   # ISO
    r"|^(?:\[\d{2}:\d{2}:\d{2}\]\s*)"                                # [12:34:56]
    r"|^(?:\d{2}:\d{2}:\d{2}\.\d+\s+)",                              # 12:34:56.789
    re.M,
)
CARRIAGE_PROGRESS = re.compile(r"^.*\r(?!\n)", re.M)     # progress bars overwriting themselves
DOWNLOAD_NOISE = re.compile(
    r"^\s*(?:Downloading|Fetching|Receiving|Resolving|Unpacking|Extracting|"
    r"Pulling|Downloaded|Get:|Selecting|Preparing to unpack|"
    r"\d+%\s*[\[\|#=\.]+|\s*[\d.]+ [KMG]iB/s).*$",
    re.M | re.I,
)
BLANK_RUNS = re.compile(r"\n{3,}")


def clean(text: str) -> str:
    """Strip presentation noise. Content is never altered — only decoration."""
    text = ANSI.sub("", text)
    text = CARRIAGE_PROGRESS.sub("", text)
    text = GITLAB_SECTION.sub("", text)
    text = GITHUB_CMD.sub("", text)
    text = TIMESTAMP_PREFIX.sub("", text)
    text = DOWNLOAD_NOISE.sub("", text)
    text = BLANK_RUNS.sub("\n\n", text)
    return text.strip()
```

> **Strip timestamps, but only the line *prefix*.** A timestamp inside an error message ("token expired at 2026-08-30T14:00:00Z") is evidence. The per-line prefix that every CI runner prepends is noise, and leaving it in wastes roughly 20% of your token budget on information the model cannot use.

---

## 7.3 Error extraction

The core value: find the ~40 lines that matter in 48,000.

```python
# ready — app/services/log_processor.py  (extraction half)
import re
from dataclasses import dataclass

# Ordered by specificity. The first family that matches wins.
ERROR_MARKERS: list[tuple[str, re.Pattern[str]]] = [
    ("php",    re.compile(r"^(PHP )?(Fatal error|Parse error|Uncaught \w+Exception|"
                          r"SQLSTATE\[\w+\])", re.M | re.I)),
    ("node",   re.compile(r"^(npm ERR!|yarn error|ERR_\w+|"
                          r"(Type|Reference|Range|Syntax)Error:|Cannot find module)", re.M)),
    ("python", re.compile(r"^(Traceback \(most recent call last\):|"
                          r"\w*Error: |\w*Exception: |E\s{3}\w+Error)", re.M)),
    ("java",   re.compile(r"^(Exception in thread|Caused by:|\s+at [\w.$]+\([\w.]+:\d+\)|"
                          r"\[ERROR\])", re.M)),
    ("go",     re.compile(r"^(panic: |# \S+\n.*\.go:\d+:|FAIL\s+\S+)", re.M)),
    ("docker", re.compile(r"^(ERROR \[|failed to solve|no space left on device|"
                          r"manifest unknown|pull access denied|"
                          r"Cannot connect to the Docker daemon)", re.M | re.I)),
    ("k8s",    re.compile(r"(ImagePullBackOff|CrashLoopBackOff|OOMKilled|"
                          r"error: unable to|FailedScheduling)", re.M)),
    ("db",     re.compile(r"(SQLSTATE|ECONNREFUSED|connection refused|"
                          r"could not connect to server|Access denied for user|"
                          r"too many connections)", re.M | re.I)),
    ("test",   re.compile(r"^(FAIL|FAILED|✕|✗|●.*›|Tests:.*failed|"
                          r"Failures:|AssertionError|Expected .* (but )?[Rr]eceived)", re.M)),
    ("shell",  re.compile(r"(command not found|Permission denied|No such file or directory|"
                          r"Killed|Segmentation fault|exit (code|status) [1-9])", re.M | re.I)),
    ("generic",re.compile(r"^(ERROR|FATAL|CRITICAL|error:|fatal:)\b", re.M | re.I)),
]

STACK_TRACE = {
    "python": re.compile(r"Traceback \(most recent call last\):[\s\S]{0,4000}?"
                         r"^\w*(Error|Exception)[^\n]*", re.M),
    "java":   re.compile(r"^(?:Exception in thread|Caused by:)[\s\S]{0,4000}?"
                         r"(?=\n\S|\Z)", re.M),
    "php":    re.compile(r"^#0 [\s\S]{0,4000}?(?=\n\n|\Z)", re.M),
    "node":   re.compile(r"^\s+at [\w.$<>\[\] ]+ \([^)]+\)(?:\n\s+at .+)*", re.M),
    "go":     re.compile(r"^panic: [\s\S]{0,4000}?(?=\n\n|\Z)", re.M),
}

EXIT_CODE = re.compile(r"(?:exit(?:ed)?(?: with)?(?: code| status)?|ERROR: Job failed: exit code)"
                       r"\s*[:=]?\s*(\d{1,3})", re.I)


@dataclass
class Extraction:
    excerpt: str
    excerpt_start_line: int
    excerpt_end_line: int
    error_block: str | None
    stack_trace: str | None
    ecosystem: str | None
    exit_code: int | None
    error_message: str | None
    matched_lines: list[int]


def extract(cleaned: str, *, context: int = 15, max_chars: int = 60_000) -> Extraction:
    lines = cleaned.split("\n")

    ecosystem, hits = None, []
    for name, pattern in ERROR_MARKERS:
        hits = [i for i, ln in enumerate(lines) if pattern.search(ln)]
        if hits:
            ecosystem = name
            break

    if not hits:
        # No marker matched. The error is almost always at the end — take the tail.
        start = max(0, len(lines) - 120)
        excerpt = "\n".join(lines[start:])
        return Extraction(
            excerpt=excerpt[-max_chars:], excerpt_start_line=start + 1,
            excerpt_end_line=len(lines), error_block=None, stack_trace=None,
            ecosystem=None, exit_code=_exit_code(cleaned),
            error_message=_last_meaningful(lines), matched_lines=[],
        )

    # Window around the FIRST error. Later errors are usually cascading consequences
    # of the first one; leading with the tail teaches the model the wrong cause.
    first, last = hits[0], hits[-1]
    start = max(0, first - context)
    end = min(len(lines), last + context + 1)

    # A huge span means the "errors" are repetitive (e.g. 400 failing assertions).
    # Keep the head of the span plus the tail of the log instead of the whole thing.
    if end - start > 400:
        end = min(len(lines), first + 200)
        excerpt = "\n".join(lines[start:end]) + "\n…\n" + "\n".join(lines[-40:])
    else:
        excerpt = "\n".join(lines[start:end])

    block = "\n".join(lines[first:min(len(lines), first + 30)])

    trace = None
    if ecosystem in STACK_TRACE:
        m = STACK_TRACE[ecosystem].search(cleaned)
        trace = m.group(0)[:4000] if m else None

    return Extraction(
        excerpt=excerpt[:max_chars],
        excerpt_start_line=start + 1,
        excerpt_end_line=end,
        error_block=block,
        stack_trace=trace,
        ecosystem=ecosystem,
        exit_code=_exit_code(cleaned),
        error_message=lines[first].strip()[:500],
        matched_lines=[h + 1 for h in hits[:50]],
    )


def _exit_code(text: str) -> int | None:
    codes = EXIT_CODE.findall(text)
    return int(codes[-1]) if codes else None


def _last_meaningful(lines: list[str]) -> str | None:
    for ln in reversed(lines):
        s = ln.strip()
        if len(s) > 10 and not s.startswith(("$", "+", "#")):
            return s[:500]
    return None
```

> **Always window the *first* error, never the last.** A dependency conflict at line 400 produces a build failure at line 8,000 and a "job failed" at line 8,100. Feeding the model the tail gets you a confident, useless analysis of the symptom. `matched_lines` is what the frontend highlights, so the developer sees why this window was chosen.

- [ ] `clean()` and `extract()` implemented
- [ ] Tested against all five fixture logs from file 05
- [ ] For each fixture, assert the excerpt contains the known root-cause line

---

## 7.4 Failure signature

The load-bearing column from file 02. Same bug, same hash, every time.

```python
# ready — app/services/signature.py
import hashlib
import re

# Order matters: broad patterns last, or they swallow the specific ones.
NORMALIZERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\[REDACTED[_A-Z]*\]"),                     "<SECRET>"),
    (re.compile(r"\b[0-9a-f]{40}\b", re.I),                  "<SHA>"),
    (re.compile(r"\bsha256:[0-9a-f]{64}\b", re.I),           "<DIGEST>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                r"[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),        "<UUID>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"), "<TIMESTAMP>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"),    "<IP>"),
    (re.compile(r"\b[a-f0-9]{12}\b", re.I),                  "<CONTAINER_ID>"),
    (re.compile(r"(/[\w.\-]+){2,}"),                         "<PATH>"),
    (re.compile(r"\b\d+(?:\.\d+){2,}\b"),                    "<VERSION>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I),                   "<HEX>"),
    (re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m|h|MB|GB|KB|MiB|GiB|KiB)\b", re.I), "<QUANTITY>"),
    (re.compile(r"\b\d{3,}\b"),                              "<NUM>"),
]

# Keep small integers — "exit code 1" vs "exit code 137" are genuinely different failures.
KEEP_SMALL_INTS = True

WHITESPACE = re.compile(r"\s+")


def normalize(error_text: str, *, max_chars: int = 2000) -> str:
    text = error_text.strip()[:max_chars]

    for pattern, token in NORMALIZERS:
        text = pattern.sub(token, text)

    if not KEEP_SMALL_INTS:
        text = re.sub(r"\b\d+\b", "<N>", text)

    return WHITESPACE.sub(" ", text).strip().lower()


def signature_hash(error_text: str, *, ecosystem: str | None = None) -> tuple[str, str]:
    """Return (sha256_hash, normalized_text).

    The ecosystem is part of the hash: an identical 'connection refused' string
    from a Docker daemon and from Postgres are different problems with different fixes.
    """
    normalized = normalize(error_text)
    payload = f"{ecosystem or 'unknown'}::{normalized}"

    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), normalized
```

**Test the invariants, not the implementation:**

```python
# ready — tests/unit/test_signature.py
def test_same_error_different_run_same_hash():
    a = "SQLSTATE[HY000] [2002] Connection refused at /app/src/Db.php:42 (2026-08-30T14:00:00Z)"
    b = "SQLSTATE[HY000] [2002] Connection refused at /srv/lib/Db.php:87 (2026-08-31T09:14:22Z)"
    assert signature_hash(a, ecosystem="db")[0] == signature_hash(b, ecosystem="db")[0]


def test_different_errors_different_hash():
    a = "SQLSTATE[HY000] [2002] Connection refused"
    b = "SQLSTATE[42S02] Base table or view not found"
    assert signature_hash(a, ecosystem="db")[0] != signature_hash(b, ecosystem="db")[0]


def test_ecosystem_separates_identical_text():
    e = "connection refused"
    assert signature_hash(e, ecosystem="db")[0] != signature_hash(e, ecosystem="docker")[0]


def test_exit_codes_stay_distinct():
    # 137 is OOM-kill, 1 is a normal failure. Collapsing them loses the diagnosis.
    assert (signature_hash("process exited with code 1")[0]
            != signature_hash("process exited with code 137")[0])
```

> **Tuning guidance:** if `occurrence_count` on a signature is always 1, you are under-normalizing (paths or numbers still varying). If distinct bugs share a signature, you are over-normalizing. Check with:
> ```sql
> SELECT occurrence_count, count(*) FROM failure_signatures GROUP BY 1 ORDER BY 1;
> ```
> A healthy distribution is a long tail of 1s with a meaningful head of repeat offenders. All-1s means the hash is useless; a handful of signatures covering everything means it is too coarse.

- [ ] `signature.py` implemented
- [ ] All four invariant tests pass

---

## 7.5 The endpoint

```python
# ready — app/api/logs.py
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings
from app.services import log_processor, redactor, signature

router = APIRouter(tags=["logs"])


class ProcessLogRequest(BaseModel):
    raw_log: str
    job_name: str | None = None
    stage_name: str | None = None
    exit_code: int | None = None
    strict_redaction: bool = True


class ProcessLogResponse(BaseModel):
    excerpt: str
    excerpt_start_line: int
    excerpt_end_line: int
    error_block: str | None = None
    stack_trace: str | None = None
    error_message: str | None = None
    ecosystem: str | None = None
    exit_code: int | None = None
    matched_lines: list[int] = Field(default_factory=list)

    signature_hash: str
    normalized_error: str

    is_redacted: bool
    redaction_count: int
    redaction_types: list[str] = Field(default_factory=list)

    original_chars: int
    excerpt_chars: int
    reduction_ratio: float


@router.post("/logs/process", response_model=ProcessLogResponse)
async def process_log(req: ProcessLogRequest) -> ProcessLogResponse:
    original_len = len(req.raw_log)

    # 1. REDACT FIRST. Everything downstream copies this text around.
    red = redactor.redact(req.raw_log, strict=req.strict_redaction)

    # 2. clean
    cleaned = log_processor.clean(red.text)

    # 3. extract
    ex = log_processor.extract(
        cleaned,
        context=settings().excerpt_context_lines,
        max_chars=settings().max_log_chars,
    )

    # 4. signature — from the error block, not the whole excerpt.
    #    Including surrounding context would make every occurrence unique.
    basis = ex.error_block or ex.error_message or cleaned[-2000:]
    sig_hash, normalized = signature.signature_hash(basis, ecosystem=ex.ecosystem)

    return ProcessLogResponse(
        excerpt=ex.excerpt,
        excerpt_start_line=ex.excerpt_start_line,
        excerpt_end_line=ex.excerpt_end_line,
        error_block=ex.error_block,
        stack_trace=ex.stack_trace,
        error_message=ex.error_message,
        ecosystem=ex.ecosystem,
        exit_code=ex.exit_code or req.exit_code,
        matched_lines=ex.matched_lines,
        signature_hash=sig_hash,
        normalized_error=normalized,
        is_redacted=red.count > 0,
        redaction_count=red.count,
        redaction_types=red.types,
        original_chars=original_len,
        excerpt_chars=len(ex.excerpt),
        reduction_ratio=round(1 - len(ex.excerpt) / max(original_len, 1), 4),
    )
```

- [ ] Endpoint implemented and wired into `app/api/router.py`
- [ ] Laravel's `ProcessJobLog` job (file 05) calls it and persists every field

---

## 7.6 Benchmark

You need a number for the report, and a regression guard.

```python
# spec — scripts/benchmark_processing.py
# For each fixture in tests/fixtures/logs/:
#   original lines/chars → excerpt lines/chars → reduction %
#   whether the known root-cause line survived (the correctness check)
#   redaction count + types
#   processing latency
# Emit a markdown table into PipeMind-data/experiments/log-processing-v1.md
```

Target profile:

| Metric | Target |
|---|---|
| Size reduction | > 95% |
| Root-cause line retained | **100%** — a miss here is a silent correctness bug |
| Processing latency | < 250 ms for a 10 MB log |
| False redactions of SHAs/digests | 0 |

> Reduction percentage is the easy number and the least important one. The one that matters is *root-cause retention*: an excerpt that is 99.9% smaller but drops the actual error has made the system worse, not cheaper. Track both, and treat retention as a hard gate.

- [ ] Benchmark script written, results committed to `PipeMind-data/experiments/`

---

## Definition of Done

```bash
# unit tests
pytest tests/unit -v                       # redaction, cleaning, extraction, signature

# real log through the endpoint
curl -s -X POST localhost:8001/v1/logs/process \
  -H "X-PipeMind-Token: $SERVICE_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"raw_log\": $(jq -Rs . < tests/fixtures/logs/failed-db-test.log)}" | jq '{
    reduction_ratio, ecosystem, error_message, signature_hash,
    redaction_count, redaction_types, excerpt_chars
  }'

# leak check — must print nothing
curl -s -X POST localhost:8001/v1/logs/process \
  -H "X-PipeMind-Token: $SERVICE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"raw_log":"DB_PASSWORD=hunter2\nAWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nexport TOKEN=ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' \
  | grep -E 'hunter2|AKIAIOSFODNN7EXAMPLE|ghp_aaaa'

# end to end through Laravel
# trigger FAIL_MODE=database in the lab, then:
php artisan tinker --execute="
  \$l = App\Models\JobLog::withoutGlobalScopes()->latest('id')->first();
  echo 'redacted='.(\$l->is_redacted?'y':'n')
      .' size='.\$l->size_bytes.' excerpt='.strlen(\$l->excerpt)
      .' sig='.substr(\$l->job->failure?->signature?->hash ?? '-', 0, 12).PHP_EOL;
"
```

- [ ] Unit tests green
- [ ] The leak check outputs nothing
- [ ] A real ingested failure has an excerpt, an error block, and a signature
- [ ] Two runs of the same failure produce the **same** `signature_hash` and `occurrence_count = 2`

**Next:** [`08-ai-classification.md`](08-ai-classification.md)
