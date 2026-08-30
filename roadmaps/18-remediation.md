# 18 — Remediation

**Repo:** `PipeMind-back` + `PipeMind-front` · **Depends on:** 17 · **Milestone:** M5

From recommendation to executed action, through a deterministic policy gate and a human approval when the policy demands one. **Laravel is the execution boundary — the AI never touches infrastructure.**

---

## 18.1 Policy engine

```php
// ready — app/Services/Remediation/RemediationPolicyEvaluator.php
namespace App\Services\Remediation;

use App\Models\{Failure, Project, Recommendation, RemediationPolicy};

class RemediationPolicyEvaluator
{
    public function evaluate(Recommendation $rec, Failure $failure): PolicyDecision
    {
        $project = $failure->project;

        $policy = RemediationPolicy::query()
            ->where('team_id', $project->team_id)
            ->where('action_type', $rec->action_type)
            ->where(fn ($q) => $q->where('project_id', $project->id)->orWhereNull('project_id'))
            ->orderByRaw('project_id IS NULL')      // project override beats the team default
            ->first();

        // No policy = forbidden. Fail closed: an action nobody has authorised
        // must never execute just because the table has a gap.
        if (! $policy || ! $policy->enabled) {
            return PolicyDecision::forbidden('No enabled policy for this action type.');
        }

        if ($policy->mode === 'forbidden') {
            return PolicyDecision::forbidden("{$rec->action_type} is not permitted in this workspace.");
        }

        if ($this->riskExceeds($rec->risk, $policy->max_risk)) {
            return PolicyDecision::requiresApproval(
                "Risk {$rec->risk} exceeds the automatic limit ({$policy->max_risk})."
            );
        }

        if (($rec->confidence ?? 0) < $policy->min_confidence) {
            return PolicyDecision::requiresApproval(
                sprintf('Confidence %.0f%% is below the %.0f%% threshold.',
                    ($rec->confidence ?? 0) * 100, $policy->min_confidence * 100)
            );
        }

        $ref = $failure->pipeline->ref;

        if ($this->matchesAny($ref, $policy->blocked_branches)) {
            return PolicyDecision::requiresApproval("Branch '{$ref}' requires explicit approval.");
        }

        if (! $this->matchesAny($ref, $policy->allowed_branches)) {
            return PolicyDecision::requiresApproval("Branch '{$ref}' is not in the allowed list.");
        }

        // Rate limit: a remediation loop that retries forever is worse than no remediation.
        $today = Remediation::where('project_id', $project->id)
            ->where('action_type', $rec->action_type)
            ->whereDate('created_at', today())
            ->whereIn('status', ['approved', 'executing', 'succeeded'])
            ->count();

        if ($today >= $policy->max_per_day) {
            return PolicyDecision::requiresApproval(
                "Daily automatic limit reached ({$policy->max_per_day})."
            );
        }

        return $policy->mode === 'auto'
            ? PolicyDecision::autoAllowed('Within policy.')
            : PolicyDecision::requiresApproval('This action always requires approval.');
    }
}
```

**Invariants — write tests for every one:**

1. Missing policy → forbidden. Never a default-allow.
2. Risk comes from the action type (file 09), never from the model.
3. The default branch escalates risk one level.
4. Daily limits count approved *and* executed actions, so an approval loop can't bypass them.
5. Project policy overrides team policy; neither can exceed `forbidden`.

- [ ] `RemediationPolicyEvaluator` + `PolicyDecision` value object
- [ ] Test per invariant
- [ ] Decision annotated on every recommendation at persist time (file 10)

---

## 18.2 Executors

```php
// ready — app/Services/Remediation/Executors/RemediationExecutor.php
interface RemediationExecutor
{
    public static function actionType(): string;

    /** Pre-flight: is this action still valid? Pipelines get retried by humans too. */
    public function canExecute(Remediation $r): bool;

    public function execute(Remediation $r): ExecutionResult;
}
```

| Executor | Action | Implementation |
|---|---|---|
| `RetryJobExecutor` | `retry_job` | `provider->retryJob()`; links the new pipeline |
| `RetryPipelineExecutor` | `retry_pipeline` | `provider->retryPipeline()` |
| `CreateIssueExecutor` | `create_issue` | `provider->createIssue()` with the analysis as the body |
| `CreateMergeRequestExecutor` | `create_merge_request` | branch → commit patch → MR. **Never pushes to the default branch.** |
| `InvestigateExecutor` | `investigate` | no-op; marks acknowledged |

```php
// ready — app/Jobs/ExecuteRemediation.php
public function handle(RemediationExecutorRegistry $registry): void
{
    $remediation = Remediation::withoutGlobalScopes()->with('project.team')->findOrFail($this->id);

    withTeam($remediation->project->team, function () use ($remediation, $registry) {

        // Re-check the policy at execution time. An approval granted an hour ago
        // must not execute under a policy that has since been tightened.
        $decision = app(RemediationPolicyEvaluator::class)
            ->evaluate($remediation->recommendation, $remediation->failure);

        if ($decision->isForbidden()) {
            $remediation->update(['status' => 'cancelled', 'error' => $decision->reason]);
            return;
        }

        $executor = $registry->for($remediation->action_type);

        if (! $executor->canExecute($remediation)) {
            $remediation->update([
                'status' => 'cancelled',
                'error'  => 'Preconditions no longer hold (already retried, or pipeline changed).',
            ]);
            return;
        }

        $remediation->update(['status' => 'executing', 'executed_at' => now()]);
        $remediation->appendAudit('executing', auth()->id());

        try {
            $result = $executor->execute($remediation);

            $remediation->update([
                'status'                => 'succeeded',
                'result'                => $result->toArray(),
                'resulting_pipeline_id' => $result->pipelineId,
                'completed_at'          => now(),
            ]);

            // The outcome closes the learning loop: if the retried pipeline goes green,
            // this resolution is evidence, and the signature can be promoted to known.
            if ($result->pipelineId) {
                WatchRemediationOutcome::dispatch($remediation->id)->delay(now()->addMinutes(2));
            }
        }
        catch (\Throwable $e) {
            $remediation->update([
                'status' => 'failed',
                'error'  => Str::limit($e->getMessage(), 1000),
                'completed_at' => now(),
            ]);
            throw $e;
        }
    });
}
```

`WatchRemediationOutcome` polls the resulting pipeline until terminal, sets `outcome_success`, and on success promotes the signature (`is_known = true`, `known_resolution` = the recommendation title).

- [ ] Five executors + registry
- [ ] `ExecuteRemediation` and `WatchRemediationOutcome` jobs
- [ ] Full audit trail appended at every transition

---

## 18.3 Approval flow

```text
Recommendation
      │
   [Apply] ──► POST /recommendations/{r}/accept
      │
      ▼
Policy evaluated
      │
   ┌──┴───────────────┬────────────────┐
   ▼                  ▼                ▼
auto_allowed   requires_approval   forbidden
   │                  │                │
   │           pending_approval    403 + reason
   │           notify approvers        │
   │                  │                ✗
   │           [Approve] / [Reject]
   │                  │
   └──────────┬───────┘
              ▼
      ExecuteRemediation (queue)
              ▼
      succeeded / failed
              ▼
      WatchRemediationOutcome → signature promoted
```

**Rules:**
- Approvals expire after 24 h (`expires_at`). A stale approval executing against a moved-on codebase is a hazard.
- The requester cannot approve their own request (file 04 policy).
- Rejection requires a reason; it is stored and shown on the recommendation.
- Every state change writes to `audit` and to `activity_logs`.

---

## 18.4 Frontend

```text
/app/projects/:slug/remediation

┌─ Pending approval (2) ──────────────────────────────────────────┐
│ ⚠ Add a database readiness healthcheck            MEDIUM RISK   │
│   Requested by PipeMind · 4 min ago · expires in 23h            │
│   Failure: DATABASE / Connection refused · #821                 │
│   Modifies: docker-compose.yml                                  │
│   ⓘ Risk medium exceeds the automatic limit (low)               │
│                          [View diff] [Reject] [Approve & run]   │
└─────────────────────────────────────────────────────────────────┘

┌─ Recent ────────────────────────────────────────────────────────┐
│ ✓ Retry job backend-tests    auto · 2h ago · pipeline #820 ✓    │
│ ✗ Create merge request       failed · 1d ago · permission denied│
└─────────────────────────────────────────────────────────────────┘
```

```vue
<!-- ready — src/components/remediation/ApprovalDialog.vue -->
<template>
  <PmModal :title="`Approve: ${remediation.recommendation.title}`" size="lg">
    <!-- Say exactly what will happen, in plain language, before the button.
         "Apply Fix" with no visible consequence is how trust gets destroyed. -->
    <PmAlert :tone="riskTone" class="mb-4">
      <strong>{{ riskLabel }}</strong> — {{ consequenceSentence }}
    </PmAlert>

    <dl class="grid grid-cols-[130px_1fr] gap-y-2 text-sm">
      <dt class="text-dim">Action</dt>       <dd>{{ actionLabel }}</dd>
      <dt class="text-dim">Target</dt>       <dd>{{ remediation.project.name }} · {{ ref }}</dd>
      <dt class="text-dim">Files</dt>        <dd><code v-for="f in files" :key="f">{{ f }}</code></dd>
      <dt class="text-dim">Confidence</dt>   <dd>{{ Math.round(confidence * 100) }}%</dd>
      <dt class="text-dim">Policy</dt>       <dd>{{ remediation.policy_reason }}</dd>
      <dt class="text-dim">Requested by</dt> <dd>{{ requester }}</dd>
    </dl>

    <PatchDiff v-if="patch" :patch="patch" class="mt-4" />

    <template #footer>
      <PmButton variant="ghost" @click="close">Cancel</PmButton>
      <PmButton variant="danger" @click="reject">Reject</PmButton>
      <PmButton variant="primary" :loading="submitting" @click="approve">
        Approve &amp; run
      </PmButton>
    </template>
  </PmModal>
</template>
```

- [ ] `RemediationView`, `ApprovalDialog`, `PatchDiff`, `PolicyNotice`, `RiskBadge` built
- [ ] Pending count badges the sidebar and the topbar bell
- [ ] Live updates via `remediation.pending` / `RemediationStatusChanged`
- [ ] Policy settings UI (owner only) with a reset-to-defaults action

---

## Definition of Done

- [ ] `retry_job` at low risk on a feature branch executes automatically and links the new pipeline
- [ ] `edit_file` requires approval and shows the policy reason
- [ ] `rollback_deployment` is refused with a clear message
- [ ] The requester cannot approve their own request
- [ ] An expired approval refuses to execute
- [ ] A retry that goes green promotes the signature to `is_known`
- [ ] Tightening a policy cancels an already-approved but unexecuted remediation
- [ ] Every transition appears in the audit trail and the activity feed

**Next:** [`19-anomaly-analytics.md`](19-anomaly-analytics.md)
