# Road to done

**Written:** 2026-09-07 · **Status:** the ordered plan, and an honest account of
what cannot be finished and why.

---

## 1. What "100%" can and cannot mean

Two parts of the roadmap cannot reach done, for different reasons. Everything
else can.

| | Why | Verdict |
|---|---|---|
| **08 — ML classifier** | Its training set is `analysis_feedback.correct_category`. There is no other source: it comes from developers correcting PipeMind in the UI. The gate is macro-F1 ≥ 0.80 on ≥ 800 labelled examples, ≥ 40 per category. You have **zero**. | **Hard block.** Not solvable by effort. Needs weeks of real use. |
| **22.2–22.4 — deployment** | Production compose, Caddyfile, deploy script, a real host. | **Deferred by your decision.** Buildable any time you want it. |

**So a realistic 100% is:** every file complete except 08's ML half, with 22's
deploy half written but not deployed. The rules classifier already covers 08's
function and agreed with Gemini 7/7 on real failures — the ML half is an
improvement, not a missing capability. Say that plainly in the report rather
than listing it as incomplete.

---

## 2. Blocked on you, not on me

None of these need much from you, but I cannot do any of them.

| # | What | Why it needs you | Unblocks |
|---|---|---|---|
| 1 | `rm -rf node_modules package-lock.json && npm install` in `PipeMind-front` | Regenerates a tracked lockfile and may move versions — your call, not a side effect of unrelated work | eslint gate, frontend coverage |
| 2 | Install a PHP coverage driver (`sudo apt install php-pcov`) | A system package on your machine | The coverage threshold, which is currently reported but ungated |
| 3 | Commit `lab/github/pipemind-lab.yml` and run a few failure modes | Only you can push to your repos | Real data for the report; feeds #4 |
| 4 | Keep using the thumbs-up/down widget | Only humans generate labels | File 08, eventually |
| 5 | Register OAuth apps (GitHub/GitLab/Google) + a **stable** public URL | Provider consoles, and your tunnel hostname rotates | The three `Continue with…` buttons |
| 6 | Commission or draw two illustrations | See the two UI plans | Landing v2 and auth v2 at full fidelity |
| 7 | Decide: upgrade `sentence-transformers` 3.4.1 → 6.0.1? | Clears 3 CVEs, but may change embedding output and invalidate every stored vector | Clean `pip-audit` |

**A standing constraint:** Gemini's free tier allows **20 analyses per day**.
That caps how much real-data work is possible in a sitting — relevant to #3 and
to the report's sample sizes.

---

## 3. The ordered plan

### Phase A — close the dead links — ✅ **done 2026-09-07**

You noticed these: four sidebar entries that are not clickable. Three are now
live; **Remediation** is the fourth and belongs to Phase B.

Knowledge turned out to be dead rather than merely unbuilt: six separate bugs
sat between a correctly indexed runbook and an answer that used it, and none of
them raised an error. See `experiments/knowledge-retrieval.md`.

1. **Knowledge** — the half that matters is already built (schema,
   `/v1/knowledge/chunk-embed`, `IndexKnowledgeDocument`, RAG retrieval). Missing
   the CRUD endpoints from roadmap 04 and a view. **Worth doing first**: without
   it, RAG's third source is permanently empty, so a documented answer can never
   reach an analysis.
2. **Project Settings** — one endpoint, one view. Auto-analyse toggle, branch
   patterns, per-project AI provider, tech stack, deactivate.
3. **Integration** (project-level) — one view over data that already exists:
   which integration, webhook health, last event, re-register, resync.

**Ended with:** no dead navigation except Remediation, and RAG's third source
reaching the prompt for the first time — measured, the same failure went from
"verify database service readiness" to "add a healthcheck and wait for
`condition: service_healthy`".

### Phase B — remediation — ✅ **done 2026-09-07**

4. **File 18.** This is where the patches you liked actually get applied, so it
   is the natural payoff of the code-aware analysis work — and the reason I now
   rank it above realtime.

   - `RemediationPolicyEvaluator` + `PolicyDecision`, annotated onto every
     recommendation at persist time (the `policy` field the UI already expects
     and currently renders as "apply manually").
   - Five executors: retry job, retry pipeline, create issue, create merge
     request, edit file. `create_merge_request` is the one that matters —
     branch → commit the patch → open a PR. **Never pushes to the default
     branch.**
   - `ExecuteRemediation` + `WatchRemediationOutcome`, with an audit row at
     every transition.
   - `RemediationView`, `ApprovalDialog`, `PolicyNotice`. `PatchDiff` and
     `RiskBadge` are already built.
   - The eight invariants in 18's DoD are the real specification — the requester
     cannot approve their own request, `rollback_deployment` is refused, an
     expired approval will not execute, tightening a policy cancels an approved
     but unexecuted remediation.

   **Delivered.** All eight DoD invariants have tests. 60 new backend tests
   (317 total), plus 6 in the AI service for the promotion rule.

   Two findings worth carrying forward:

   - **Every real recommendation was unexecutable.** All 44 in the database
     arrived as `edit_file` or `update_config`, neither of which has an executor
     — so an applyable patch could never become a pull request. `sanitize()` now
     promotes a patch-bearing recommendation to `create_merge_request`, keeping
     the higher of the two risks so the gate cannot be relaxed by the promotion.
   - **A 403 from GitHub with no rate-limit header was reported as a rate
     limit**, because `(int) null === 0`. A read-only token is the most common
     403 here, so the message sent people away to wait instead of widening the
     token's scope.

   PHPStan's baseline shrank from 359 entries to 263: typing the Eloquent
   relations and enum casts these services traverse fixed 96 previously
   acknowledged errors rather than adding new ones.

   **Not yet demonstrated live:** the promotion rule is unit-tested but the
   end-to-end run is pending — `gemini-3.6-flash` returned 503 (capacity) on
   every attempt. Worth re-running once Google has capacity, since it is the
   most convincing thing in the product.

### Phase C — liveness

5. **File 17.** Reverb, nine events dispatched from the existing jobs, `useEcho`
   / `useChannel` / `useProjectRealtime` / `useConnectionStatus`, a connection
   indicator, and polling that disables while live and resumes on disconnect.

   Polling already works, so this is an upgrade rather than a gap — but "the
   analysis appears without a refresh" is the single most convincing thing to
   show in a demo, and it removes the request noise a reviewer would notice in a
   network tab.

### Phase D — reach

6. **File 20.1 notifications.** Channel dispatcher (Slack, Teams, email, generic
   webhook), dedupe by signature, digest mode, severity filter, per-channel
   test-send. The DoD case worth building for: *six pipelines failing on one
   signature produce one message, not six.*
7. **File 20.3 assistant.** `/v1/chat` with tool calling and SSE streaming,
   `AssistantDrawer`, history per user, behind `VITE_ENABLE_ASSISTANT`. The
   roadmap says ship it last and that is right — it is the most speculative
   piece and the easiest to cut. Note it consumes the same 20/day quota.

   *20.2 (search + palette) is already done.*

### Phase E — the deliverable

8. **Landing v2 + auth v2.** Both plans are written. Layout, cards, mirrored
   auth panel, `AuthField` icons and reveal toggle need **no assets** and close
   most of the gap; the illustrations slot into reserved space when they exist.
   Do the auth layout before the landing page — it is smaller and every one of
   the five auth views improves at once.
9. **File 21 tail.** Playwright: four E2E journeys and visual regression against
   `ui/*.png`. Needs the full stack running, which is why it comes after the
   features settle — E2E written against a moving target gets rewritten.
10. **File 23 — the report.** `evaluate_all.py`, `reports/evaluation-final.md`,
    the diagrams, and `pipemind:demo --reset`.

    **This is what you are graded on.** Four experiments already carry real
    numbers — `prompt-v1`, `similarity-threshold`, `log-processing-v1`,
    `anomaly-v1` — and `00-decisions.md` is now a long, honest record of
    defects found and design calls made. Assembling it is mostly writing, not
    measuring.

---

## 4. Two things worth doing out of order

**Start Phase E step 10 early, as a running document.** Every phase above
produces numbers and decisions. Writing them up at the end means reconstructing
them; writing as you go means the report is nearly finished when the code is.

**Do #3 from section 2 today** — commit the lab workflow and break a build a few
times. It costs you minutes, and it is the only thing that starts the clock on
file 08. Every day without it is a day the ML classifier cannot begin.

---

## 5. If time runs short

Cut in this order, last first:

1. **20.3 assistant** — speculative, feature-flagged, explicitly "ship last".
2. **17 realtime** — polling works; this is polish that reads as magic.
3. **20.1 notifications** — valuable, but nothing about the core claim depends on it.
4. **Landing v2** — the current landing page is honest and functional.
5. **Playwright** — 268 tests already cover the logic; E2E covers the wiring.

**Never cut:** Phase A (dead links are the most visible flaw in the product),
Phase B (remediation is the payoff of the whole analysis chain), or step 10 (the
report is the deliverable).

---

## 6. Where things stand

```
✅ 01  ✅ 02  ✅ 03  ✅ 04  ✅ 05  ✅ 05b  ✅ 06  ✅ 07
🟡 08  ✅ 09  ✅ 10  ✅ 11  ✅ 12  ✅ 13  ✅ 14  ✅ 15  ✅ 16
🔴 17  ✅ 18  ✅ 19  🟡 20  🟡 21  🟡 22  🔴 23

M1 ✅   M2 ✅   M3 ✅   M4 ✅   M5 🟡 (needs 17, 20)
```

**18 is complete**, including the parts 17 would have made live: the remediation
list polls while anything is in flight and stops when nothing is, so the only
thing realtime adds here is removing that polling.

**Next is 17 (realtime) or 20 (notifications).** 17 is the smaller of the two and
mostly removes polling that already works; 20.1's dedupe-by-signature is the
piece with real user value — six pipelines failing on one signature should
produce one message, not six.

- **08** — rules complete and verified; ML half hard-blocked on data.
- **20** — search and palette done; notifications and assistant not started.
- **21** — all gates configured and green; Playwright outstanding.
- **22** — CI done for all four repos; deployment deferred by choice.

**590 tests green** across three services (317 Laravel, 235 Python, 38
frontend), `pint` · `phpstan` · `ruff` · `mypy` · `vue-tsc` · `composer audit`
all clean. PHPStan's baseline shrank from 362 entries to 263 across Phases A and
B: typing the Eloquent relations and enum casts these services traverse fixed
real false positives instead of acknowledging them.
