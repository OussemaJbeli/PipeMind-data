# Group 1 — Identity & Tenancy

`users` · `teams` · `team_user` · `team_invitations`

## Purpose

Who can see what. A **team** is the tenancy boundary: every tenant-scoped table carries
`team_id`, enforced by a Laravel global scope.

## Key decisions

**Multi-tenancy from day one.** Retrofitting tenancy is a rewrite, not a migration.
Even a single-user deployment gets a team.

**`teams.privacy_mode`** decides whether logs may reach an external LLM.
`local_only` forces a local provider; if none is configured the analysis fails loudly
rather than silently falling back to the cloud. Enforced in Laravel — the boundary
belongs on the side that owns the team record.

**`teams.monthly_ai_budget_usd`** is a hard stop checked before every model call
(not sampled). Exceeding it raises `AI_BUDGET_EXCEEDED`, which is deliberately
non-retryable — the point of a budget is that it stops you.

**`users.current_team_id`** is a nullable self-referencing FK added after `teams`
exists, breaking the circular dependency between the two tables.

## Roles

| Capability | owner | admin | member | viewer |
|---|:--:|:--:|:--:|:--:|
| View everything | ✓ | ✓ | ✓ | ✓ |
| Trigger analysis, retry jobs | ✓ | ✓ | ✓ | — |
| Approve remediation | ✓ | ✓ | — | — |
| Manage projects, integrations, AI providers, members | ✓ | ✓ | — | — |
| Edit remediation policies | ✓ | — | — | — |
| Delete team | ✓ | — | — | — |

The API returns a flat `permissions` array derived from this matrix. The frontend calls
`can('remediation.approve')` and never reimplements the role logic — one source of truth.

## Gotchas

- `teams.owner_id` is `ON DELETE RESTRICT`: a user who owns a team cannot be deleted
  until ownership transfers. Deliberate — the alternative is orphaned workspaces.
- `team_invitations` is unique on `(team_id, email)`. Re-inviting refreshes the existing
  row rather than creating duplicates.
- Queue jobs have no authenticated user, so the global scope is inert. **Every job must
  wrap its work in `withTeam()`** or it silently operates across all tenants. This is the
  most likely source of a cross-tenant leak in the whole system.
