# 08 — Failure Classification

**Repo:** `PipeMind-ai` + `PipeMind-data` · **Depends on:** 07 · **Milestone:** M3

Determine *what kind* of failure this is, cheaply and measurably. Start with rules, build a labeled dataset, train a baseline, and only adopt something more sophisticated when it beats the baseline on the same holdout.

> **The trap this file exists to avoid:** reaching for a transformer because it sounds better in a report, without ever measuring the 200 lines of regex it replaced. A rule engine that hits 0.84 F1 in 3 ms is not embarrassing — it is the thing your fancy model has to beat.

---

## 8.1 Taxonomy

Write `PipeMind-data/taxonomy/failure-categories.md` first — everything downstream depends on the labels being fixed.

| Category | Subcategories | Signature examples |
|---|---|---|
| `BUILD` | Compilation, Bundling, Linting, TypeCheck, AssetGeneration | `error TS2345:`, `webpack build failed`, `Compilation error` |
| `TEST` | UnitTest, IntegrationTest, E2ETest, Assertion, Coverage, Snapshot | `FAIL login.test.ts`, `Expected 200 Received 401`, `Coverage below threshold` |
| `DEPENDENCY` | Conflict, NotFound, VersionMismatch, RegistryError, LockfileDrift, AuditFail | `ERESOLVE unable to resolve`, `Cannot find module`, `composer requires` |
| `DATABASE` | ConnectionRefused, AuthFailed, MigrationError, SchemaMismatch, Timeout, Deadlock | `SQLSTATE[HY000] [2002]`, `relation does not exist`, `deadlock detected` |
| `NETWORK` | Timeout, DNSFailure, ConnectionReset, ProxyError, TLSError | `ETIMEDOUT`, `getaddrinfo ENOTFOUND`, `certificate has expired` |
| `DOCKER` | BuildFailed, ImageNotFound, RegistryAuth, DiskSpace, DaemonUnavailable, LayerError | `no space left on device`, `pull access denied`, `failed to solve` |
| `DEPLOYMENT` | HealthCheckFailed, RolloutTimeout, RollbackTriggered, EnvMismatch | `CrashLoopBackOff`, `rollout timed out`, `readiness probe failed` |
| `CONFIGURATION` | MissingEnvVar, InvalidYAML, WrongPath, MissingSecret, InvalidValue | `variable not set`, `yaml: line 12: mapping values`, `no such file` |
| `AUTHENTICATION` | InvalidToken, ExpiredToken, MissingToken, Unauthorized, MFARequired | `401 Unauthorized`, `token expired`, `authentication required` |
| `PERMISSION` | FilePermission, RegistryPermission, RepoPermission, SudoRequired | `Permission denied`, `EACCES`, `403 Forbidden` |
| `INFRASTRUCTURE` | RunnerUnavailable, NodeFailure, QuotaExceeded, ServiceDown | `no runner matched`, `job was cancelled by the system` |
| `RESOURCE` | OutOfMemory, DiskFull, CPUThrottle, FileDescriptors, Timeout | `OOMKilled`, `exit code 137`, `JavaScript heap out of memory` |
| `UNKNOWN` | — | anything below the confidence floor |

**Labeling rules — write these down or your dataset becomes inconsistent:**

1. Label the **root cause**, not the symptom. A test that fails because the DB is down is `DATABASE`, not `TEST`.
2. When two apply, pick the one whose **fix** is correct. A dependency conflict surfacing as a build error is `DEPENDENCY` — you fix `package.json`, not the compiler.
3. `UNKNOWN` is a real label, not a failure. Forcing a guess pollutes every other class.
4. `RESOURCE` beats everything when OOM or disk-full is present — it explains the rest.

- [ ] `taxonomy/failure-categories.md` written with 3 real log examples per subcategory

---

## 8.2 Rule classifier

```python
# ready — app/services/classifier/rules.py
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    category: str
    subcategory: str
    pattern: re.Pattern[str]
    weight: float = 1.0
    # ecosystems this rule is valid in; None = any
    ecosystems: tuple[str, ...] | None = None


def _p(s: str) -> re.Pattern[str]:
    return re.compile(s, re.IGNORECASE | re.MULTILINE)


RULES: list[Rule] = [
    # ---- RESOURCE: checked first, it explains other symptoms ----
    Rule("RESOURCE", "OutOfMemory", _p(r"OOMKilled|out of memory|Cannot allocate memory|"
                                       r"JavaScript heap out of memory|exit code 137|"
                                       r"java\.lang\.OutOfMemoryError"), 1.0),
    Rule("RESOURCE", "DiskFull",    _p(r"no space left on device|ENOSPC|disk quota exceeded"), 1.0),

    # ---- DATABASE ----
    Rule("DATABASE", "ConnectionRefused",
         _p(r"SQLSTATE\[HY000\]\s*\[2002\]|could not connect to server|"
            r"ECONNREFUSED.*:(5432|3306|27017|1433)|"
            r"Connection refused.*(postgres|mysql|mariadb|mongo)"), 1.0),
    Rule("DATABASE", "AuthFailed",
         _p(r"password authentication failed|Access denied for user|"
            r"SQLSTATE\[28000\]|authentication failed for user"), 1.0),
    Rule("DATABASE", "MigrationError",
         _p(r"Migration .* failed|relation \"?\w+\"? already exists|"
            r"SQLSTATE\[42S02\]|relation \"?\w+\"? does not exist|"
            r"Base table or view not found"), 0.95),
    Rule("DATABASE", "Deadlock", _p(r"deadlock detected|Lock wait timeout exceeded"), 1.0),

    # ---- DEPENDENCY ----
    Rule("DEPENDENCY", "Conflict",
         _p(r"ERESOLVE|unable to resolve dependency tree|"
            r"Your requirements could not be resolved|version solving failed|"
            r"conflicting peer dependency"), 1.0),
    Rule("DEPENDENCY", "NotFound",
         _p(r"Cannot find module|Module not found|"
            r"Could not find a version that satisfies|"
            r"404 Not Found.*(npm|registry|packagist|pypi)|"
            r"package \S+ is not installed"), 0.95),
    Rule("DEPENDENCY", "LockfileDrift",
         _p(r"lock file .* out of date|composer\.lock is not up to date|"
            r"npm ci can only install .* package-lock\.json"), 1.0),
    Rule("DEPENDENCY", "RegistryError",
         _p(r"(npm|yarn|pip|composer) ERR!.*(ETIMEDOUT|ECONNRESET|registry)"), 0.85),

    # ---- DOCKER ----
    Rule("DOCKER", "RegistryAuth",
         _p(r"pull access denied|unauthorized: authentication required|"
            r"denied: requested access to the resource is denied|manifest unknown"), 1.0),
    Rule("DOCKER", "BuildFailed",
         _p(r"failed to solve|ERROR \[\d+/\d+\]|"
            r"The command '/bin/sh -c .*' returned a non-zero code"), 0.9),
    Rule("DOCKER", "DaemonUnavailable",
         _p(r"Cannot connect to the Docker daemon|docker: error during connect"), 1.0),

    # ---- NETWORK ----
    Rule("NETWORK", "DNSFailure", _p(r"getaddrinfo (ENOTFOUND|EAI_AGAIN)|"
                                     r"Temporary failure in name resolution|"
                                     r"Could not resolve host"), 1.0),
    Rule("NETWORK", "Timeout",    _p(r"ETIMEDOUT|Connection timed out|"
                                     r"Operation timed out|context deadline exceeded"), 0.85),
    Rule("NETWORK", "TLSError",   _p(r"certificate (has expired|verify failed)|"
                                     r"x509:|SSL_ERROR|unable to get local issuer certificate"), 1.0),
    Rule("NETWORK", "ConnectionReset", _p(r"ECONNRESET|Connection reset by peer|"
                                          r"broken pipe"), 0.8),

    # ---- AUTHENTICATION ----
    Rule("AUTHENTICATION", "InvalidToken",
         _p(r"401 Unauthorized|invalid[_ ]token|Bad credentials|"
            r"authentication (failed|required)|HTTP 401"), 0.9),
    Rule("AUTHENTICATION", "ExpiredToken",
         _p(r"token (has )?expired|credentials have expired|JWT expired"), 1.0),

    # ---- PERMISSION ----
    Rule("PERMISSION", "FilePermission", _p(r"EACCES|Permission denied(?!.*401)|"
                                            r"Operation not permitted"), 0.9),
    Rule("PERMISSION", "RepoPermission", _p(r"403 Forbidden|insufficient (scope|permission)|"
                                            r"You are not allowed to push"), 0.9),

    # ---- CONFIGURATION ----
    Rule("CONFIGURATION", "MissingEnvVar",
         _p(r"(environment )?variable \S+ (is )?not (set|defined)|"
            r"\$\{?\w+\}?: unbound variable|required env"), 1.0),
    Rule("CONFIGURATION", "InvalidYAML",
         _p(r"yaml: line \d+|mapping values are not allowed|"
            r"did not find expected key|Invalid CI config"), 1.0),
    Rule("CONFIGURATION", "WrongPath",
         _p(r"No such file or directory|cannot stat|"
            r"ENOENT: no such file"), 0.7),

    # ---- DEPLOYMENT ----
    Rule("DEPLOYMENT", "HealthCheckFailed",
         _p(r"readiness probe failed|liveness probe failed|health check failed|"
            r"CrashLoopBackOff"), 1.0),
    Rule("DEPLOYMENT", "RolloutTimeout",
         _p(r"rollout .* timed out|deployment .* exceeded its progress deadline"), 1.0),

    # ---- INFRASTRUCTURE ----
    Rule("INFRASTRUCTURE", "RunnerUnavailable",
         _p(r"no (active )?runner|This job is stuck|"
            r"job was cancelled by the system|runner system failure"), 1.0),
    Rule("INFRASTRUCTURE", "QuotaExceeded",
         _p(r"quota exceeded|rate limit exceeded|429 Too Many Requests|"
            r"API rate limit"), 0.9),

    # ---- BUILD ----
    Rule("BUILD", "TypeCheck", _p(r"error TS\d+:|Type error:|mypy: error"), 1.0),
    Rule("BUILD", "Compilation", _p(r"compilation (failed|error)|"
                                    r"syntax error|Parse error:|"
                                    r"PHP Fatal error:.*syntax"), 0.9),
    Rule("BUILD", "Linting", _p(r"eslint.*\d+ problems?|"
                                r"PHP_CodeSniffer.*ERRORS?|"
                                r"ruff.*Found \d+ error"), 0.95),

    # ---- TEST: last, because a test failure is often a symptom ----
    Rule("TEST", "Assertion",
         _p(r"AssertionError|Expected .*(but )?(received|got|actual)|"
            r"expect\(.*\)\.to|assertEquals|Failed asserting that"), 0.8),
    Rule("TEST", "UnitTest",
         _p(r"^(FAIL|FAILED|✕|✗)\s|Tests?:.*\d+ failed|"
            r"Failures: [1-9]|\d+ failing"), 0.7),
    Rule("TEST", "E2ETest",
         _p(r"(cypress|playwright|selenium|puppeteer).*(failed|error)|"
            r"Timed out retrying after \d+ms"), 0.85),
]


@dataclass
class RuleResult:
    category: str
    subcategory: str | None
    confidence: float
    matched_rules: list[str]


class RuleClassifier:
    """Deterministic, ~2 ms, no model. The baseline everything else must beat."""

    @staticmethod
    def warm() -> None:
        for r in RULES:
            r.pattern.search("")

    def classify(self, text: str, ecosystem: str | None = None) -> RuleResult:
        scores: dict[tuple[str, str], float] = {}
        matched: list[str] = []

        for rule in RULES:
            if rule.ecosystems and ecosystem not in rule.ecosystems:
                continue

            hits = len(rule.pattern.findall(text))
            if not hits:
                continue

            key = (rule.category, rule.subcategory)
            # Diminishing returns: 10 matches is not 10× the evidence of one.
            scores[key] = scores.get(key, 0.0) + rule.weight * min(1.0 + (hits - 1) * 0.1, 1.5)
            matched.append(f"{rule.category}/{rule.subcategory}")

        if not scores:
            return RuleResult("UNKNOWN", None, 0.0, [])

        (cat, sub), best = max(scores.items(), key=lambda kv: kv[1])
        total = sum(scores.values())

        # Confidence = dominance of the winner, not its raw score. A rule that fires
        # alone is far more trustworthy than one that ties with three others.
        confidence = min(0.98, (best / total) * min(best / 1.0, 1.0))

        return RuleResult(cat, sub, round(confidence, 3), sorted(set(matched)))
```

> **`RESOURCE` first, `TEST` last** is the whole ordering philosophy. OOM explains everything downstream of it; a failing test explains nothing on its own. When rules tie, the earlier declaration wins because the list is ordered by explanatory power.

- [ ] `rules.py` implemented with ≥ 35 rules
- [ ] One unit test per category using a real log excerpt

---

## 8.3 Dataset

Three sources, in increasing order of value.

### Source 1 — synthetic (start here, available today)

```python
# spec — scripts/generate_synthetic.py
# Uses the FAIL_MODE lab from file 01. For each mode, run the pipeline,
# capture the real log, record the known category. Extend the matrix:
#
#   FAIL_MODE          category        subcategory
#   dependency         DEPENDENCY      Conflict
#   dependency-404     DEPENDENCY      NotFound
#   database           DATABASE        ConnectionRefused
#   database-auth      DATABASE        AuthFailed
#   test-assert        TEST            Assertion
#   docker-space       DOCKER          BuildFailed  (via RESOURCE DiskFull)
#   docker-auth        DOCKER          RegistryAuth
#   network-dns        NETWORK         DNSFailure
#   oom                RESOURCE        OutOfMemory
#   env-missing        CONFIGURATION   MissingEnvVar
#   yaml-invalid       CONFIGURATION   InvalidYAML
#   perm-denied        PERMISSION      FilePermission
#   token-expired      AUTHENTICATION  ExpiredToken
#   timeout            NETWORK         Timeout
#
# Output: datasets/raw/synthetic/{mode}/{run_id}.log + labels.jsonl
# Vary: project language, log length, surrounding noise, runner image.
```

> These are **real logs from real failures** — the failure was induced deliberately, but the tooling produced genuine output. That is categorically different from asking a model to write a log that looks plausible, which teaches your classifier the model's writing style rather than npm's.

### Source 2 — public CI logs

```python
# spec — scripts/harvest_public.py
# GitHub Actions logs from public repos with failed runs.
#   GET /repos/{owner}/{repo}/actions/runs?status=failure
#   GET /repos/{owner}/{repo}/actions/runs/{id}/jobs
#   GET /repos/{owner}/{repo}/actions/jobs/{id}/logs
# Sample across ecosystems: node, php, python, go, java, rust.
# Redact on ingest (file 07) before anything touches disk.
# Record: repo, run id, url, harvest date → provenance for the report.
```

Respect rate limits, only public repos, and record provenance. Note in your report that these are third-party public logs used for research.

### Source 3 — your own production data (the best, arrives last)

`analysis_feedback.correct_category` from file 02. Every time a developer corrects PipeMind, you gain a perfectly in-domain labeled example. Export it:

```sql
-- ready — export corrected labels as ground truth
SELECT
    f.uuid,
    s.normalized_error,
    jl.error_block,
    jl.stack_trace,
    COALESCE(af.correct_category, a.category) AS label,
    f.subcategory,
    (af.correct_category IS NOT NULL) AS human_verified
FROM failures f
JOIN analyses a           ON a.failure_id = f.id
LEFT JOIN analysis_feedback af ON af.analysis_id = a.id
LEFT JOIN failure_signatures s ON s.id = f.signature_id
LEFT JOIN pipeline_jobs pj     ON pj.id = f.job_id
LEFT JOIN job_logs jl          ON jl.job_id = pj.id
WHERE af.correct_category IS NOT NULL
   OR a.confidence >= 0.90;
```

### Format

```jsonl
{"id":"syn-0001","text":"npm ERR! ERESOLVE unable to resolve dependency tree\nnpm ERR! While resolving: frontend@1.0.0\nnpm ERR! Found: vue@3.5.0\nnpm ERR! peer vue@\"^2.0.0\" from package-x","ecosystem":"node","category":"DEPENDENCY","subcategory":"Conflict","source":"synthetic","human_verified":true,"created_at":"2026-08-30"}
```

```text
PipeMind-data/datasets/
├── raw/synthetic/          per-mode logs + labels.jsonl
├── raw/public/             harvested, redacted, with provenance.json
├── processed/              cleaned + extracted (file 07 applied)
├── classification/
│   ├── train.jsonl         70%
│   ├── val.jsonl           15%
│   ├── test.jsonl          15%  ← touched ONCE, at the end
│   └── DATASET.md          version, counts, class distribution, known limitations
```

**Splitting rule that matters most:** split by **signature hash**, never randomly by row. The same error appearing 40 times must land entirely in one split. Random splitting puts near-identical rows in train and test, and your reported accuracy becomes a memorization score.

```python
# ready — scripts/dataset.py (the split)
import hashlib

def split_key(record: dict) -> str:
    """Group by signature so identical failures never straddle a split."""
    return record.get("signature_hash") or hashlib.sha256(
        record["text"][:500].encode()
    ).hexdigest()


def stratified_group_split(records, ratios=(0.70, 0.15, 0.15), seed=42):
    """Group-aware, class-stratified. Groups are assigned whole."""
    import random
    from collections import defaultdict

    groups = defaultdict(list)
    for r in records:
        groups[split_key(r)].append(r)

    by_class = defaultdict(list)
    for key, items in groups.items():
        by_class[items[0]["category"]].append(key)

    rng = random.Random(seed)
    train, val, test = [], [], []

    for _, keys in by_class.items():
        rng.shuffle(keys)
        n = len(keys)
        n_tr, n_va = int(n * ratios[0]), int(n * ratios[1])
        for bucket, ks in ((train, keys[:n_tr]), (val, keys[n_tr:n_tr+n_va]), (test, keys[n_tr+n_va:])):
            for k in ks:
                bucket.extend(groups[k])

    return train, val, test
```

- [ ] ≥ 800 labeled examples, ≥ 40 per category
- [ ] Split by signature group, stratified by class
- [ ] `DATASET.md` records version, counts, distribution, sources, limitations

> **Class imbalance is the failure mode here.** If 60% of your data is `TEST`, a model that always predicts `TEST` scores 60% accuracy and is worthless. Report **macro-F1** and the per-class table, never overall accuracy alone. Deliberately over-collect rare categories.

---

## 8.4 ML classifier

```python
# ready — app/services/classifier/ml.py
from dataclasses import dataclass
from pathlib import Path

import joblib

MODEL_PATH = Path("models/classifier_v1.joblib")


@dataclass
class MLResult:
    category: str
    confidence: float
    probabilities: dict[str, float]


class MLClassifier:
    def __init__(self) -> None:
        self._pipeline = None

    def available(self) -> bool:
        return MODEL_PATH.exists()

    def _load(self):
        if self._pipeline is None:
            self._pipeline = joblib.load(MODEL_PATH)
        return self._pipeline

    def classify(self, text: str) -> MLResult | None:
        if not self.available():
            return None

        pipe = self._load()
        probs = pipe.predict_proba([text])[0]
        classes = pipe.classes_
        ranked = sorted(zip(classes, probs), key=lambda kv: kv[1], reverse=True)

        return MLResult(
            category=str(ranked[0][0]),
            confidence=float(ranked[0][1]),
            probabilities={str(c): float(p) for c, p in ranked[:5]},
        )
```

```python
# ready — scripts/train.py
import json
from pathlib import Path

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

DATA = Path("../PipeMind-data/datasets/classification")


def load(split: str):
    rows = [json.loads(l) for l in (DATA / f"{split}.jsonl").read_text().splitlines() if l]
    return [r["text"] for r in rows], [r["category"] for r in rows]


def build(kind: str = "logreg") -> Pipeline:
    vec = TfidfVectorizer(
        # Character n-grams beat word n-grams on logs: error strings are full of
        # punctuation, paths and codes that word tokenizers destroy.
        analyzer="char_wb",
        ngram_range=(3, 5),
        max_features=50_000,
        min_df=2,
        sublinear_tf=True,
        lowercase=True,
    )

    clf = (
        LogisticRegression(max_iter=2000, class_weight="balanced", C=4.0)
        if kind == "logreg"
        else CalibratedClassifierCV(LinearSVC(class_weight="balanced"), cv=3)
    )

    return Pipeline([("tfidf", vec), ("clf", clf)])


if __name__ == "__main__":
    Xtr, ytr = load("train")
    Xva, yva = load("val")

    best, best_score = None, -1.0
    for kind in ("logreg", "svc"):
        pipe = build(kind)
        pipe.fit(Xtr, ytr)

        from sklearn.metrics import f1_score
        score = f1_score(yva, pipe.predict(Xva), average="macro")
        print(f"{kind}: macro-F1 = {score:.4f}")

        if score > best_score:
            best, best_score = pipe, score

    Path("models").mkdir(exist_ok=True)
    joblib.dump(best, "models/classifier_v1.joblib")
    print(f"saved. best val macro-F1 = {best_score:.4f}")
```

> **`class_weight="balanced"` and `char_wb` n-grams are the two decisions that matter.** Balanced weighting stops the majority class from eating everything; character n-grams handle `SQLSTATE[HY000]` and `ERESOLVE` as the meaningful tokens they are, where a word tokenizer sees punctuation soup.

```python
# ready — scripts/evaluate.py
import json
from pathlib import Path

import joblib
from sklearn.metrics import (classification_report, confusion_matrix, f1_score)

DATA = Path("../PipeMind-data/datasets/classification")
OUT = Path("../PipeMind-data/experiments")


def main() -> None:
    rows = [json.loads(l) for l in (DATA / "test.jsonl").read_text().splitlines() if l]
    X = [r["text"] for r in rows]
    y = [r["category"] for r in rows]

    from app.services.classifier.rules import RuleClassifier
    rules = RuleClassifier()
    y_rules = [rules.classify(t).category for t in X]

    pipe = joblib.load("models/classifier_v1.joblib")
    y_ml = list(pipe.predict(X))

    lines = ["# Classification — v1 evaluation", "",
             f"Test set: {len(y)} samples, {len(set(y))} classes", "",
             "## Headline", "",
             "| Model | Macro-F1 | Weighted-F1 | Accuracy |", "|---|---|---|---|"]

    for name, pred in (("Rules", y_rules), ("TF-IDF + LinearModel", y_ml)):
        acc = sum(a == b for a, b in zip(pred, y)) / len(y)
        lines.append(
            f"| {name} | {f1_score(y, pred, average='macro'):.3f} "
            f"| {f1_score(y, pred, average='weighted'):.3f} | {acc:.3f} |"
        )

    for name, pred in (("Rules", y_rules), ("ML", y_ml)):
        lines += ["", f"## Per class — {name}", "", "```",
                  classification_report(y, pred, zero_division=0), "```"]

    labels = sorted(set(y))
    cm = confusion_matrix(y, y_ml, labels=labels)
    lines += ["", "## Confusion matrix — ML", "",
              "| actual \\ pred | " + " | ".join(labels) + " |",
              "|---" * (len(labels) + 1) + "|"]
    for lab, row in zip(labels, cm):
        lines.append(f"| **{lab}** | " + " | ".join(str(v) for v in row) + " |")

    OUT.mkdir(exist_ok=True)
    (OUT / "classification-v1.md").write_text("\n".join(lines))
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    main()
```

- [ ] `train.py` and `evaluate.py` written
- [ ] Results committed to `PipeMind-data/experiments/classification-v1.md`
- [ ] Confusion matrix inspected — the interesting question is *which pairs* confuse

**What the confusion matrix will tell you** (and what to do about it):

| Confusion | Meaning | Fix |
|---|---|---|
| `TEST` ↔ `DATABASE` | Symptom vs root cause | More context in the excerpt; label rule 1 |
| `DEPENDENCY` ↔ `BUILD` | Conflict surfacing as compile error | Weight `DEPENDENCY` rules higher |
| `NETWORK` ↔ `INFRASTRUCTURE` | Genuinely ambiguous | Consider merging the subcategories |
| Everything → majority class | Imbalance | More rare-class data, check `class_weight` |

---

## 8.5 Hybrid strategy

```python
# ready — app/services/classifier/hybrid.py
from dataclasses import dataclass

from app.services.classifier.ml import MLClassifier
from app.services.classifier.rules import RuleClassifier


@dataclass
class Classification:
    category: str
    subcategory: str | None
    confidence: float
    source: str                # rules | ml | hybrid | llm
    matched_rules: list[str]
    probabilities: dict[str, float]


class HybridClassifier:
    """Cheapest sufficient answer wins. The LLM is a fallback, not the default."""

    HIGH = 0.85
    LOW = 0.50

    def __init__(self) -> None:
        self.rules = RuleClassifier()
        self.ml = MLClassifier()

    def classify(self, text: str, ecosystem: str | None = None) -> Classification:
        r = self.rules.classify(text, ecosystem)

        # A confident rule hit is final. It is deterministic, explainable and free.
        if r.confidence >= self.HIGH:
            return Classification(r.category, r.subcategory, r.confidence,
                                  "rules", r.matched_rules, {})

        m = self.ml.classify(text)

        if m is None:
            return Classification(r.category, r.subcategory, r.confidence,
                                  "rules", r.matched_rules, {})

        # Agreement between two independent methods is worth more than either alone.
        if m.category == r.category and r.confidence > 0:
            return Classification(
                r.category, r.subcategory,
                min(0.97, max(r.confidence, m.confidence) + 0.10),
                "hybrid", r.matched_rules, m.probabilities,
            )

        if m.confidence >= self.HIGH:
            return Classification(m.category, None, m.confidence, "ml", [], m.probabilities)

        # Both unsure — hand it to the LLM, which sees full context the classifiers don't.
        if max(r.confidence, m.confidence) < self.LOW:
            return Classification("UNKNOWN", None, max(r.confidence, m.confidence),
                                  "llm", r.matched_rules, m.probabilities)

        return (Classification(r.category, r.subcategory, r.confidence, "rules",
                               r.matched_rules, m.probabilities)
                if r.confidence >= m.confidence
                else Classification(m.category, None, m.confidence, "ml", [], m.probabilities))
```

> **`classification_source` is stored on every analysis** (file 02) so you can answer, with data, "how often did we actually need the LLM?" If the answer is 8%, your rules and baseline are carrying the system and your token bill stays trivial. That number belongs in your report.

```python
# ready — app/api/classify.py
@router.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    result = HybridClassifier().classify(req.text, req.ecosystem)

    return ClassifyResponse(
        category=result.category,
        subcategory=result.subcategory,
        confidence=result.confidence,
        source=result.source,
        matched_rules=result.matched_rules,
        probabilities=result.probabilities,
    )
```

- [ ] `HybridClassifier` implemented
- [ ] `/v1/classify` live
- [ ] Laravel's `ProcessJobLog` calls it and stores category + subcategory on the signature

---

## 8.6 The experiment record

Write `PipeMind-data/experiments/classification-v1.md` as a real experiment report, not a results dump:

```markdown
# Experiment: Failure Classification v1

## Question
Can a cheap deterministic classifier match an LLM on CI failure categorization?

## Dataset
v0.3 — 847 samples, 13 classes, split by signature group, stratified.
Sources: 612 synthetic (lab-induced), 198 public GitHub Actions, 37 human-verified production.
Known limitations: DEPLOYMENT and INFRASTRUCTURE under-represented (n=41, n=38).

## Models
A — Rule engine, 37 regex rules, ordered by explanatory power
B — TF-IDF char_wb(3,5) + LogisticRegression, class_weight=balanced
C — Hybrid (A→B→LLM escalation)
D — LLM-only (gemini-2.0-flash, zero-shot with the taxonomy in the prompt)

## Results
| Model | Macro-F1 | Weighted-F1 | Latency p50 | Cost / 1k |
|---|---|---|---|---|
| A |  |  | ~2 ms | $0 |
| B |  |  | ~8 ms | $0 |
| C |  |  |  |  |
| D |  |  |  |  |

## Decision
…which model shipped, and why. Include the case *against* the winner.

## What surprised us
…the most valuable section. Write it honestly.
```

- [ ] Experiment written with real numbers
- [ ] Include the LLM-only arm — you need the comparison to justify not using it everywhere

---

## Definition of Done

```bash
# dataset
wc -l ../PipeMind-data/datasets/classification/*.jsonl
python -c "
import json,collections,pathlib
p=pathlib.Path('../PipeMind-data/datasets/classification/train.jsonl')
c=collections.Counter(json.loads(l)['category'] for l in p.read_text().splitlines() if l)
[print(f'{k:16} {v}') for k,v in c.most_common()]
"

# train + evaluate
python scripts/train.py
python scripts/evaluate.py

# no group leakage between train and test
python -c "
import json,pathlib
d=pathlib.Path('../PipeMind-data/datasets/classification')
g=lambda f:{json.loads(l).get('signature_hash') for l in (d/f).read_text().splitlines() if l}
assert not (g('train.jsonl') & g('test.jsonl')), 'LEAKAGE'
print('no leakage')
"

# endpoint
curl -s -X POST localhost:8001/v1/classify \
  -H "X-PipeMind-Token: $SERVICE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"npm ERR! ERESOLVE unable to resolve dependency tree\npeer vue@\"^2.0.0\" from package-x","ecosystem":"node"}' | jq .
# expect: DEPENDENCY / Conflict, source "rules", confidence > 0.85
```

- [ ] Macro-F1 ≥ 0.80 for the shipped model on the held-out test set
- [ ] Zero group leakage
- [ ] Experiment report committed with the LLM-only comparison

**Next:** [`09-ai-llm-rag.md`](09-ai-llm-rag.md)
