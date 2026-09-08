"""Produces reports/evaluation-final.md from live data.

One script, one output, reproducible. Reads the same database the application
writes, so every number in the report traces to a row somebody can go and look
at.

Its second job is to be honest about what it CANNOT measure. Several headline
metrics in roadmaps/23 need ground truth that only accumulates through real use
— human-graded root causes, corrected categories, anomalies marked as false
positives. Those sections print what is missing and how much of it is needed,
rather than a plausible-looking number derived from nothing. A report claiming
96% on everything reads as untested.
"""

from __future__ import annotations

import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    import psycopg
except ImportError:
    sys.exit("psycopg is required: pip install 'psycopg[binary]'")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "evaluation-final.md"

# Enough labelled examples for a per-class score to mean anything, from
# roadmaps/08: macro-F1 over >= 800 examples with >= 40 per category.
MIN_LABELS_FOR_F1 = 800
MIN_GRADED_FOR_CALIBRATION = 50


def dsn() -> str:
    url = os.environ.get("DATABASE_URL")

    if url:
        return url.replace("postgresql+psycopg://", "postgresql://")

    return (
        f"host={os.environ.get('DB_HOST', '127.0.0.1')} "
        f"port={os.environ.get('DB_PORT', '5434')} "
        f"dbname={os.environ.get('DB_DATABASE', 'pipemind')} "
        f"user={os.environ.get('DB_USERNAME', 'pipemind')} "
        f"password={os.environ.get('DB_PASSWORD', 'pipemind')}"
    )


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.blocked: list[tuple[str, str]] = []

    def h(self, level: int, text: str) -> None:
        self.lines.append(f"\n{'#' * level} {text}\n")

    def p(self, text: str) -> None:
        self.lines.append(text + "\n")

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        self.lines.append("| " + " | ".join(headers) + " |")
        self.lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in rows:
            self.lines.append("| " + " | ".join(str(c) for c in row) + " |")
        self.lines.append("")

    def block(self, section: str, needed: str) -> None:
        """Records a metric that cannot be computed, and what would unblock it."""
        self.blocked.append((section, needed))
        self.p(f"**Not measurable yet.** {needed}")


def scalar(cur, sql: str, default=0):
    cur.execute(sql)
    row = cur.fetchone()

    return row[0] if row and row[0] is not None else default


def cost_and_latency(cur, r: Report) -> None:
    r.h(2, "Cost and latency")

    cur.execute("""
        SELECT provider, model, count(*), sum(cost_usd), avg(latency_ms),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
        FROM ai_requests
        WHERE status = 'success' AND latency_ms IS NOT NULL
        GROUP BY provider, model ORDER BY count(*) DESC
    """)
    rows = cur.fetchall()

    if not rows:
        r.block("cost", "No successful AI requests recorded.")

        return

    r.table(
        ["provider", "model", "calls", "total $", "mean ms", "p50 ms", "p95 ms"],
        [[p, m, n, f"{(c or 0):.4f}", f"{(a or 0):.0f}", f"{(p50 or 0):.0f}", f"{(p95 or 0):.0f}"]
         for p, m, n, c, a, p50, p95 in rows],
    )

    total = scalar(cur, "SELECT count(*) FROM ai_requests WHERE status = 'success'")
    spend = scalar(cur, "SELECT sum(cost_usd) FROM ai_requests WHERE status = 'success'", 0.0)

    if total:
        r.p(f"Mean cost per successful call: **${float(spend) / total:.5f}** over {total} calls.")

    hits = scalar(cur, "SELECT count(*) FROM analyses WHERE cache_hit = true")
    analyses = scalar(cur, "SELECT count(*) FROM analyses")

    if analyses:
        r.p(
            f"Cache hit rate: **{hits / analyses:.0%}** ({hits}/{analyses}). "
            "This rises with history — a cache hit requires the same failure "
            "signature to have been analysed before, so a young workspace "
            "cannot demonstrate the steady-state figure."
        )


def classification(cur, r: Report) -> None:
    r.h(2, "Classification")

    cur.execute("""
        SELECT classification_source, count(*)
        FROM analyses WHERE classification_source IS NOT NULL
        GROUP BY classification_source ORDER BY count(*) DESC
    """)
    rows = cur.fetchall()

    if rows:
        r.p("Which arm decided the category, across all analyses:")
        r.table(["source", "n"], [[s, n] for s, n in rows])

    cur.execute("SELECT category, count(*) FROM analyses WHERE category IS NOT NULL GROUP BY category ORDER BY count(*) DESC")
    rows = cur.fetchall()

    if rows:
        r.p("Category distribution — note how uneven it is; a macro-F1 over this "
            "would be dominated by whichever classes happen to be populated:")
        r.table(["category", "n"], [[c, n] for c, n in rows])

    labels = scalar(cur, "SELECT count(*) FROM analysis_feedback WHERE correct_category IS NOT NULL")

    r.block(
        "classification F1",
        f"Macro-F1, per-class P/R/F1 and the confusion matrix need a labelled "
        f"test set. The only source of labels is `analysis_feedback.correct_category`, "
        f"written when a developer corrects PipeMind in the UI. **{labels} of "
        f"{MIN_LABELS_FOR_F1} needed** (and >= 40 per category). Until then the "
        f"rules classifier is unvalidated beyond the 7/7 agreement with the LLM "
        f"recorded in `experiments/prompt-v1.md`.",
    )


def calibration(cur, r: Report) -> None:
    r.h(2, "Confidence calibration")

    cur.execute("""
        SELECT width_bucket(confidence, 0, 1, 4) AS bucket, count(*), avg(confidence)
        FROM analyses WHERE confidence IS NOT NULL
        GROUP BY bucket ORDER BY bucket
    """)
    rows = cur.fetchall()

    if rows:
        names = {1: "0.00–0.25", 2: "0.25–0.50", 3: "0.50–0.75", 4: "0.75–1.00"}
        r.p("Stated confidence, bucketed. This is the *distribution* only — the "
            "second column of a calibration curve, 'actually correct', requires "
            "grading:")
        r.table(
            ["bucket", "n", "mean stated confidence"],
            [[names.get(b, str(b)), n, f"{float(a):.2f}"] for b, n, a in rows],
        )

    r.block(
        "calibration curve",
        f"The headline result of roadmaps/23 — does 90% confidence mean right 90% "
        f"of the time — needs {MIN_GRADED_FOR_CALIBRATION} failures with a "
        f"human-verified root cause, graded blind to the stated confidence. "
        f"**0 graded so far.** Nothing in the schema records a grade, so this "
        f"needs a grading pass and a column to hold the verdict.",
    )


def retrieval(cur, r: Report) -> None:
    r.h(2, "Retrieval")

    embeddings = scalar(cur, "SELECT count(*) FROM failure_embeddings")
    signatures = scalar(cur, "SELECT count(*) FROM failure_signatures")
    failures = scalar(cur, "SELECT count(*) FROM failures")
    chunks = scalar(cur, "SELECT count(*) FROM knowledge_chunks")

    r.table(
        ["quantity", "value"],
        [
            ["failures recorded", failures],
            ["distinct signatures", signatures],
            ["dedup ratio", f"{failures / signatures:.2f}×" if signatures else "n/a"],
            ["failure embeddings", embeddings],
            ["knowledge chunks", chunks],
        ],
    )

    r.p(
        "The dedup ratio is the signature layer working: it is how many recorded "
        "failures collapse into one distinct problem. A ratio near 1.0 means "
        "either genuinely distinct failures or a normaliser that is leaking "
        "run-scoped values — `experiments/knowledge-retrieval.md` documents one "
        "such leak that made every repeat failure look new."
    )

    r.p(
        "Threshold sensitivity was measured directly rather than inferred here; "
        "see `experiments/similarity-threshold.md` (failure-to-failure, 0.75 → "
        "0.55) and `experiments/knowledge-retrieval.md` (knowledge chunks, "
        "0.60 → 0.40, with the chunk-size and neighbour-expansion results)."
    )

    r.block(
        "precision@k and MRR",
        "Needs labelled similar/dissimilar failure pairs. None exist: the "
        "thresholds above were derived from measured score distributions on "
        "hand-built probe sets, not from a labelled retrieval benchmark.",
    )


def rag_contribution(cur, r: Report) -> None:
    r.h(2, "RAG contribution")

    used = scalar(cur, "SELECT count(*) FROM analyses WHERE used_rag = true")
    total = scalar(cur, "SELECT count(*) FROM analyses")

    if total:
        r.p(f"RAG was used in **{used}/{total}** analyses ({used / total:.0%}).")

    cur.execute("""
        SELECT used_rag, count(*), avg(confidence), avg(prompt_tokens), avg(cost_usd)
        FROM analyses WHERE confidence IS NOT NULL GROUP BY used_rag
    """)
    rows = cur.fetchall()

    if len(rows) > 1:
        r.table(
            ["used_rag", "n", "mean confidence", "mean prompt tokens", "mean $"],
            [[u, n, f"{float(c):.2f}", f"{float(p or 0):.0f}", f"{float(x or 0):.5f}"]
             for u, n, c, p, x in rows],
        )
        r.p(
            "**Confidence is not accuracy.** A difference in mean stated "
            "confidence between the two arms says the model felt more certain, "
            "not that it was more often right. The number that would justify the "
            "feature is root-cause accuracy with RAG on versus off, and that "
            "needs grading."
        )

    r.block(
        "RAG accuracy delta",
        "The same failures analysed with `use_rag` on and off, both graded. "
        "Requires the grading pass above plus a second paid run per failure.",
    )


def anomalies(cur, r: Report) -> None:
    r.h(2, "Anomaly detection")

    cur.execute("SELECT status, count(*) FROM anomalies GROUP BY status ORDER BY count(*) DESC")
    rows = cur.fetchall()

    if rows:
        r.table(["status", "n"], [[s, n] for s, n in rows])

    fp = scalar(cur, "SELECT count(*) FROM anomalies WHERE status = 'false_positive'")
    total = scalar(cur, "SELECT count(*) FROM anomalies")

    if total and fp:
        r.p(f"False-positive rate: **{fp / total:.0%}** ({fp}/{total}).")
    else:
        r.block(
            "anomaly precision and false-positive rate",
            f"`anomalies.status = 'false_positive'` is the ground truth, and it is "
            f"written only when a user pushes back on an alert in the UI. "
            f"{total} anomalies recorded, **0 marked false positive** — which is "
            f"an absence of feedback, not a precision of 100%. Reporting it as "
            f"the latter would be the single most misleading number available.",
        )

    r.p(
        "The detector's own tuning is measured in `experiments/anomaly-v1.md`: a "
        "hardcoded 1.5× memory ratio produced 22 anomalies from 24 jobs, and "
        "MAD-based scoring reduced that to 3."
    )


def end_to_end(cur, r: Report) -> None:
    r.h(2, "End-to-end latency")

    cur.execute("""
        SELECT extract(epoch FROM (a.completed_at - f.created_at))
        FROM analyses a JOIN failures f ON f.id = a.failure_id
        WHERE a.completed_at IS NOT NULL AND a.status = 'completed'
    """)
    values = [float(v[0]) for v in cur.fetchall() if v[0] is not None and 0 < float(v[0]) < 3600]

    if len(values) < 3:
        r.block("end-to-end latency", f"Only {len(values)} completed analyses with usable timestamps.")

        return

    values.sort()
    r.table(
        ["measure", "seconds"],
        [
            ["n", len(values)],
            ["p50", f"{statistics.median(values):.1f}"],
            ["p95", f"{values[int(len(values) * 0.95) - 1]:.1f}"],
            ["min", f"{values[0]:.1f}"],
            ["max", f"{values[-1]:.1f}"],
        ],
    )
    r.p(
        "Measured from the failure row being written to the analysis completing — "
        "so it includes queue wait, log fetch, redaction, classification, "
        "retrieval and the model call, but not the webhook delivery that "
        "preceded it."
    )


def provider_comparison(r: Report) -> None:
    r.h(2, "Provider comparison")
    r.block(
        "gemini vs local qwen2.5-coder",
        "Requires Ollama running locally and 30 failures replayed through both. "
        "Not run: no local provider is configured on this machine. The offline "
        "path in roadmaps/23.5 depends on the same setup.",
    )


def main() -> int:
    r = Report()

    r.lines.append("# PipeMind — evaluation results\n")
    r.p(f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `scripts/evaluate_all.py` "
        "from the live database.\n")
    r.p(
        "> Every number below is computed from rows in the running system. Where a "
        "metric cannot be computed, this report says so and states what is missing "
        "rather than estimating. The gaps are concentrated in one place — metrics "
        "that need human judgement as ground truth — and they are listed together "
        "at the end.\n"
    )

    with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
        cost_and_latency(cur, r)
        classification(cur, r)
        calibration(cur, r)
        retrieval(cur, r)
        rag_contribution(cur, r)
        anomalies(cur, r)
        end_to_end(cur, r)
        provider_comparison(r)

    r.h(2, "What this evaluation cannot yet answer")
    r.p(
        "Every blocked metric below shares one dependency: ground truth that only "
        "a human can produce. None of it is blocked on engineering.\n"
    )
    r.table(["metric", "what is needed"], [[s, n] for s, n in r.blocked])
    r.p(
        "\nThe practical consequence is that PipeMind's *accuracy* is currently "
        "unvalidated, while its *cost, latency and behaviour* are measured. A "
        "report should say exactly that."
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(r.lines))
    print(f"wrote {OUT.relative_to(ROOT)} ({len(r.lines)} lines, {len(r.blocked)} blocked metrics)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
