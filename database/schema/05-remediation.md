# Group 5 — Remediation

`remediation_policies` · `remediations`

## Purpose

Executing actions safely. **The LLM proposes; `remediation_policies` decides; Laravel
executes.** The AI never holds credentials or touches infrastructure.

## Invariants

1. **No policy = forbidden.** A gap in the table must never mean allow.
2. **Risk comes from `action_type`, assigned by code** — never from the model. A model
   that can label a production rollback "low risk" can talk its way past the safety layer.
3. **The default branch escalates risk one level.**
4. **Daily limits count approved *and* executed actions**, so an approval loop cannot
   bypass them.
5. **Project policy overrides team policy**; neither can exceed `forbidden`.
6. **The policy is re-evaluated at execution time.** An approval granted an hour ago must
   not execute under a policy that has since been tightened.

## Default policy

| action_type | mode | max_risk | min_confidence |
|---|---|---|---|
| `retry_job` | auto | low | 0.85 |
| `retry_pipeline` | approval | low | 0.85 |
| `create_issue` | auto | low | 0.70 |
| `investigate` | auto | low | 0.00 |
| `create_merge_request` | approval | medium | 0.90 |
| `edit_file` | approval | medium | 0.90 |
| `update_dependency` | approval | medium | 0.90 |
| `update_config` | approval | high | 0.95 |
| `rollback_deployment` | **forbidden** | critical | 1.00 |

## `outcome_success` closes the loop

A remediation that ran and led to a green pipeline is evidence the resolution works, and
promotes the signature to `is_known`. That is how the knowledge base grows from real
outcomes rather than from the model's assertions.

## Gotchas

- Approvals expire after 24 h. A stale approval executing against a moved-on codebase is
  a hazard.
- The requester cannot approve their own request — separation of duties, even solo. On a
  one-person team that makes `auto` mode the only path to unattended action, which is the
  correct outcome: unattended actions should be governed by a written policy, not by a
  person waving through their own request.
- `audit` (jsonb) appends at every transition. It is the answer to "who approved what,
  and what happened".
