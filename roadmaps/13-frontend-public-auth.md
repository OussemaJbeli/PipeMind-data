# 13 — Landing, Auth & Onboarding

**Repo:** `PipeMind-front` · **Depends on:** 12 · **Milestone:** M1

Everything before the workspace: the marketing landing page, the auth flow, and the onboarding wizard that gets a new user from signup to a connected project with real pipelines flowing.

---

## 13.1 Landing page — `/`

Single page, dark, same visual language as the product. The goal is one thing: make a DevOps engineer think *"that is my Tuesday"* within five seconds.

```text
┌──────────────────────────────────────────────────────────────┐
│  ◆ PipeMind      Product  How it works  Docs   [Sign in] [Get started] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│              Your pipeline failed.                           │
│              PipeMind already knows why.                     │
│                                                              │
│    An intelligence layer over GitLab, GitHub Actions and     │
│    Jenkins. It reads the logs, finds the cause, remembers    │
│    the fix.                                                  │
│                                                              │
│         [ Get started free ]   [ See a live analysis → ]     │
│                                                              │
│    ┌────────────────────────────────────────────────┐        │
│    │  ANIMATED TERMINAL → ANALYSIS CARD             │        │
│    │                                                │        │
│    │  $ git push origin feature/payment             │        │
│    │  ✗ Pipeline #821 failed · test · 2m 14s        │        │
│    │  ─────────────────────────────────────         │        │
│    │  ✦ PipeMind · 92% confidence                   │        │
│    │  Database was unavailable when integration     │        │
│    │  tests started.                                │        │
│    │  ✓ docker-compose.yml changed in this commit   │        │
│    │  ✓ Similar to failure #921 (94%) — fixed by    │        │
│    │    adding a healthcheck                        │        │
│    └────────────────────────────────────────────────┘        │
├──────────────────────────────────────────────────────────────┤
│  THE PROBLEM — 3 columns                                     │
│  48,000 log lines  ·  12 possible causes  ·  "we fixed this  │
│                                                 in March"    │
├──────────────────────────────────────────────────────────────┤
│  HOW IT WORKS — 4 numbered steps with connecting line        │
│  Connect → Observe → Analyse → Remember                      │
├──────────────────────────────────────────────────────────────┤
│  FEATURE GRID — 6 cards, icon + title + one line             │
│  Root cause · Historical memory · Anomalies · Multi-platform │
│  Safe remediation · Privacy modes                            │
├──────────────────────────────────────────────────────────────┤
│  PROVIDERS — GitLab · GitHub Actions · Jenkins · Any webhook  │
├──────────────────────────────────────────────────────────────┤
│  PRIVACY — split card: Cloud (redacted) | Local (Ollama)     │
├──────────────────────────────────────────────────────────────┤
│  CTA + footer                                                │
└──────────────────────────────────────────────────────────────┘
```

**The hero animation is the whole pitch.** Build it as a typed-out terminal that transitions into a real analysis card — the same `AnalysisCard` component the product uses, with static demo data. It shows the actual output rather than describing it, and it costs nothing extra because the component already exists.

```vue
<!-- spec — src/views/public/components/HeroDemo.vue -->
<!-- Phase 1 (0–1.5s):  type `git push origin feature/payment`
     Phase 2 (1.5–3s):  pipeline steps tick over, test turns red
     Phase 3 (3–4s):    "PipeMind is analysing…" shimmer
     Phase 4 (4s+):     the real <AnalysisCard> fades in with demo data
     Loop after 12s. Respect prefers-reduced-motion: show phase 4 immediately. -->
```

- [ ] `LandingView.vue` with the sections above
- [ ] `HeroDemo` reuses the product's `AnalysisCard`
- [ ] Reduced-motion path skips straight to the result
- [ ] Meta tags + OG image, Lighthouse performance ≥ 90

---

## 13.2 Auth layout

Split screen: form left (440px), branded panel right. The right panel shows a static analysis card and a rotating one-line quote about CI pain — quiet, not loud.

```vue
<!-- ready — src/layouts/AuthLayout.vue -->
<template>
  <div class="grid min-h-screen lg:grid-cols-[minmax(0,480px)_1fr]">
    <div class="flex flex-col justify-center px-8 py-12 sm:px-14">
      <RouterLink to="/" class="mb-10 flex items-center gap-2.5">
        <PmLogo class="size-8" />
        <span class="text-lg font-semibold">PipeMind</span>
      </RouterLink>

      <slot />
    </div>

    <!-- Decorative only; hidden below lg so the form is never squeezed. -->
    <div
      class="relative hidden overflow-hidden border-l bg-sidebar lg:block"
      aria-hidden="true"
    >
      <div class="absolute inset-0 opacity-[0.035] [background-image:radial-gradient(var(--pm-accent)_1px,transparent_1px)] [background-size:22px_22px]" />
      <div class="relative grid h-full place-items-center p-16">
        <AuthShowcase />
      </div>
    </div>
  </div>
</template>
```

---

## 13.3 Auth views

| Route | View | Notes |
|---|---|---|
| `/login` | `LoginView` | email, password, remember, forgot link |
| `/register` | `RegisterView` | name, email, password + strength meter, workspace name |
| `/forgot-password` | `ForgotPasswordView` | always shows the same success message |
| `/reset-password/:token` | `ResetPasswordView` | token from URL, email prefilled from query |
| `/invitations/:token` | `AcceptInvitationView` | shows team + inviter; registers or logs in then joins |

```vue
<!-- ready — src/views/public/LoginView.vue -->
<script setup lang="ts">
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const form = reactive({ email: '', password: '', remember: false })
const errors = ref<Record<string, string[]>>({})
const generalError = ref<string | null>(null)
const loading = ref(false)

async function submit() {
  loading.value = true
  errors.value = {}
  generalError.value = null

  try {
    await auth.login(form.email, form.password, form.remember)
    router.push((route.query.redirect as string) || { name: 'workspace' })
  }
  catch (e) {
    const err = e as ApiError
    // 422 → per-field. Everything else → one banner. Never dump a raw error object.
    if (err.validation)
      errors.value = err.validation
    else
      generalError.value = err.message
  }
  finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold">Welcome back</h1>
    <p class="mt-1.5 text-sm text-dim">Sign in to your PipeMind workspace.</p>

    <PmAlert v-if="generalError" tone="danger" class="mt-6">{{ generalError }}</PmAlert>

    <form class="mt-7 space-y-4" @submit.prevent="submit">
      <PmInput
        v-model="form.email" label="Email" type="email" autocomplete="email"
        required autofocus :error="errors.email?.[0]"
      />
      <PmInput
        v-model="form.password" label="Password" type="password"
        autocomplete="current-password" required :error="errors.password?.[0]"
      >
        <template #label-suffix>
          <RouterLink to="/forgot-password" class="text-xs text-accent hover:underline">
            Forgot?
          </RouterLink>
        </template>
      </PmInput>

      <PmToggle v-model="form.remember" label="Keep me signed in" />

      <PmButton type="submit" variant="primary" size="lg" block :loading="loading">
        Sign in
      </PmButton>
    </form>

    <p class="mt-6 text-center text-sm text-dim">
      No account?
      <RouterLink to="/register" class="text-accent hover:underline">Create one</RouterLink>
    </p>
  </div>
</template>
```

**Auth rules worth stating:**

- Forgot-password always returns the same message whether or not the email exists. Anything else is an account-enumeration oracle.
- Password strength meter is advisory; the server enforces the rule. Never let the client be the only validator.
- After login, honour `?redirect=` — a user who deep-linked to a failure should land on that failure, not the dashboard.
- Rate-limit feedback (429) shows a countdown, not a generic error.

- [ ] Five auth views built
- [ ] Validation errors render per-field
- [ ] Full flow works against the seeded backend

---

## 13.4 Onboarding — `/welcome`

Four steps. The success condition is a **real pipeline visible on the board**, not "account created".

```text
Step 1  Workspace      name, optional logo, timezone
Step 2  Connect CI     provider → credentials → verify
Step 3  Import project pick repos → register webhooks
Step 4  AI provider    Gemini key | Ollama | skip for now
        ────────────────────────────────────────────
        Waiting room:  "Push a commit and watch it land"
```

```vue
<!-- ready — src/views/onboarding/OnboardingView.vue (shape) -->
<script setup lang="ts">
const step = ref(1)
const total = 4
const state = reactive({
  workspace: { name: '', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
  integration: { provider: 'gitlab' as const, base_url: '', token: '', verified: false, uuid: '' },
  projects: [] as string[],
  ai: { provider: 'gemini', api_key: '', skipped: false },
})

// Each step persists to the server as it completes. If the user closes the tab
// at step 3, they resume at step 3 — not back at step 1 with a half-made workspace.
async function next() {
  await persistCurrentStep()
  step.value = Math.min(total, step.value + 1)
}
</script>
```

### Step 2 — the step that decides whether onboarding succeeds

```text
┌────────────────────────────────────────────────────────┐
│  Connect your CI/CD                                    │
│                                                        │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐          │
│  │ GitLab │ │ GitHub │ │Jenkins │ │ Other  │          │
│  │   🦊   │ │   🐙   │ │   ☕   │ │  ⚙️    │          │
│  └────────┘ └────────┘ └────────┘ └────────┘          │
│                                                        │
│  GitLab URL   [ https://gitlab.com              ]      │
│  Access token [ glpat-••••••••••••••••          ]      │
│                                                        │
│  ⓘ Needs scope `api`. Read-only `read_api` works for   │
│    monitoring but cannot retry jobs.                   │
│    → How to create a token                             │
│                                                        │
│  [ Test connection ]                                   │
│                                                        │
│  ✓ Connected as @oussema · 14 projects visible         │
└────────────────────────────────────────────────────────┘
```

> **Verify before advancing, and say exactly what the token can and cannot do.** Half of all integration support burden is a token with the wrong scope. Showing "connected as X, N projects visible, retry: not permitted" at connect time turns a confusing future failure into a clear present choice.

### Step 3 — import

Searchable list of remote projects with checkboxes; on submit, Laravel creates the projects **and registers the webhooks**. Show per-project webhook status, because a project imported without a working hook looks fine and does nothing.

```text
✓ biker-api      webhook registered
✓ biker-front    webhook registered
⚠ biker-legacy   webhook failed — insufficient permission   [Retry] [Skip]
```

### The waiting room

After step 4, do not dump the user on an empty dashboard. Show a live-waiting screen:

```text
        ◐  Waiting for your first pipeline

   PipeMind is connected to biker-api and listening.
   Push a commit, or run a pipeline manually.

   $ git commit --allow-empty -m "hello pipemind" && git push

   ┌──────────────────────────────────────┐
   │  Webhook endpoint    ✓ registered    │
   │  Last event          — none yet      │
   │  Listening since     just now        │
   └──────────────────────────────────────┘

              [ Skip to dashboard ]
```

Poll `/projects/{p}/pipelines` every 5 s. The moment one arrives, animate into the project board. This is the first genuinely delightful moment in the product and it costs one polling loop.

- [ ] Four-step wizard with server-side resume
- [ ] Connection verification with capability reporting
- [ ] Webhook registration status per project
- [ ] Waiting room polls and transitions on first pipeline
- [ ] `onboarded_at` set; the router guard stops redirecting

---

## Definition of Done

```bash
npm run dev
# 1. / renders, hero animation loops, reduced-motion respected
# 2. /register → new user + workspace
# 3. onboarding: connect lab GitLab → import pipemind-lab → skip AI
# 4. waiting room appears
# 5. trigger a pipeline in the lab
# 6. it appears within ~10s and the app transitions to the project board
```

- [ ] A brand-new user reaches a populated board without touching the database
- [ ] Closing the tab mid-onboarding resumes at the right step
- [ ] All auth flows work, including invitation acceptance

**Next:** [`14-frontend-workspace.md`](14-frontend-workspace.md)
