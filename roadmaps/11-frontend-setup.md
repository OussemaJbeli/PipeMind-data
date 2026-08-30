# 11 — Frontend Setup

**Repo:** `PipeMind-front` · **Depends on:** 04 · **Milestone:** M1

Vue 3 + TypeScript + Vite + Tailwind, a typed API client generated from the file-04 contract, Pinia stores, routing and guards. Built against the **seeded** backend, so no ingestion is required to make progress here.

---

## 11.1 Install

```bash
# ready
cd PipeMind-front
npm create vite@latest . -- --template vue-ts

npm i vue-router@4 pinia @vueuse/core axios \
      @tanstack/vue-query date-fns \
      chart.js vue-chartjs \
      @headlessui/vue floating-vue \
      laravel-echo pusher-js \
      nprogress

npm i -D tailwindcss @tailwindcss/vite postcss autoprefixer \
      @types/node unplugin-vue-components unplugin-auto-import \
      unplugin-icons @iconify-json/lucide @iconify-json/simple-icons \
      vue-tsc typescript eslint @antfu/eslint-config prettier \
      vitest @vue/test-utils jsdom @vitest/coverage-v8 \
      @playwright/test msw
```

**Why these and not the alternatives:**

| Choice | Reason |
|---|---|
| `@tanstack/vue-query` | Pipeline data is server state that goes stale. Query gives caching, refetch-on-focus and polling for free — Pinia would mean reimplementing all of it. |
| Pinia | Only for genuine *client* state: auth, current team, sidebar collapsed, theme. Not for API responses. |
| `chart.js` + `vue-chartjs` | The mockup needs line, bar, donut and sparkline — all four, dark-themed, in ~60 KB. D3 is more power than these charts need. |
| `unplugin-icons` + Lucide | The mockup's icon style exactly; tree-shaken to only what you import. `simple-icons` covers the GitLab fox / GitHub marks. |
| `floating-vue` | Chart tooltips and the "why this confidence" popovers. |
| `msw` | Mock the API in tests and Storybook-style development without a running backend. |

- [ ] Dependencies installed, `npm run dev` serves

---

## 11.2 Config

```ts
// ready — vite.config.ts
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import Icons from 'unplugin-icons/vite'
import IconsResolver from 'unplugin-icons/resolver'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
    AutoImport({
      imports: ['vue', 'vue-router', 'pinia', '@vueuse/core'],
      dts: 'src/types/auto-imports.d.ts',
    }),
    Components({
      dirs: ['src/components'],
      resolvers: [IconsResolver({ prefix: 'i', enabledCollections: ['lucide', 'simple-icons'] })],
      dts: 'src/types/components.d.ts',
    }),
    Icons({ compiler: 'vue3', autoInstall: false }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // Same-origin in dev so Sanctum's cookie auth works without CORS gymnastics.
      '/api':          { target: 'http://localhost:8000', changeOrigin: true },
      '/sanctum':      { target: 'http://localhost:8000', changeOrigin: true },
      '/broadcasting': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ['chart.js', 'vue-chartjs'],
          realtime: ['laravel-echo', 'pusher-js'],
        },
      },
    },
  },
})
```

> The dev proxy matters more than it looks: serving the API same-origin means Sanctum's cookie auth works without CORS configuration, and it matches how you'll deploy behind one domain in file 22.

```jsonc
// ready — tsconfig.app.json (key options)
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "verbatimModuleSyntax": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] },
    "types": ["vite/client", "unplugin-icons/types/vue"]
  }
}
```

- [ ] `vite.config.ts` and tsconfig set, `npm run build` clean

---

## 11.3 Structure

```text
src/
├── main.ts
├── App.vue
├── assets/
│   ├── tokens.css          design tokens from 00-INDEX
│   └── main.css            Tailwind + base layer
├── router/
│   ├── index.ts
│   └── guards.ts
├── stores/
│   ├── auth.ts             user, team, permissions
│   ├── ui.ts               sidebar, theme, command palette
│   └── notifications.ts    bell badge + list
├── api/
│   ├── client.ts           axios instance + interceptors
│   ├── endpoints/          one module per resource
│   └── queries/            vue-query hooks
├── types/
│   ├── api.ts              generated from the backend contract
│   ├── domain.ts           enums mirrored from PHP
│   └── charts.ts
├── composables/
│   ├── usePolling.ts
│   ├── useRelativeTime.ts
│   ├── useStatusMeta.ts    status → color + icon + label
│   ├── useCategoryMeta.ts  category → color + icon + label
│   └── useCan.ts           permission checks
├── components/
│   ├── ui/                 Button Card Badge Pill Input Select Modal Drawer …
│   ├── charts/             LineChart BarChart DonutChart Sparkline RadialGauge
│   ├── layout/             AppSidebar AppTopbar AppShell UserMenu
│   ├── workspace/          KpiTile ProjectCard ActivityFeed …
│   ├── project/            PipelineTable FailureBreakdown AiInsightCard …
│   └── failure/            EvidenceList LogViewer SimilarFailures …
├── views/
│   ├── public/             LandingView LoginView RegisterView …
│   ├── onboarding/
│   ├── workspace/          WorkspaceView ProjectsView ActivityView SettingsView
│   ├── project/            OverviewView PipelinesView FailuresView …
│   └── errors/
└── utils/
    ├── format.ts           duration, bytes, percent, relative time
    └── colors.ts
```

- [ ] Structure created

---

## 11.4 Types

Mirror the backend contract. These are hand-written once and then guarded by a test.

```ts
// ready — src/types/domain.ts
export const FAILURE_CATEGORIES = [
  'BUILD','TEST','DEPENDENCY','DATABASE','NETWORK','DOCKER','DEPLOYMENT',
  'CONFIGURATION','AUTHENTICATION','PERMISSION','INFRASTRUCTURE','RESOURCE','UNKNOWN',
] as const
export type FailureCategory = typeof FAILURE_CATEGORIES[number]

export const PIPELINE_STATUSES = [
  'queued','running','success','failed','canceled','skipped','manual','timeout',
] as const
export type PipelineStatus = typeof PIPELINE_STATUSES[number]

export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type Risk = Severity
export type TeamRole = 'owner' | 'admin' | 'member' | 'viewer'
export type Trend = 'up' | 'down' | 'flat'
export type ActivityLevel = 'info' | 'success' | 'warning' | 'error'
```

```ts
// ready — src/types/api.ts (excerpt — mirrors file 04 exactly)
export interface Metric {
  value: number
  unit?: string
  display?: string
  delta?: number
  delta_label?: string
  trend?: Trend
  /** Which direction is "good". Fewer failures is good; the UI colors arrows from this. */
  positive_direction?: 'up' | 'down'
  spark?: number[]
}

export interface WorkspaceSummary {
  projects: Metric
  pipelines_today: Metric
  failures_today: Metric
  success_rate: Metric
}

export interface ProjectCard {
  uuid: string
  name: string
  slug: string
  icon: string
  color: string
  tech_stack: string[]
  health_status: 'healthy' | 'degraded' | 'failing' | 'unknown'
  success_rate: number
  failures_today: number
  pipelines_count: number
  last_pipeline: {
    uuid: string
    iid: number
    status: PipelineStatus
    finished_at: string | null
    duration_seconds: number | null
  } | null
}

export interface ActivityItem {
  uuid: string
  action: string
  level: ActivityLevel
  title: string
  description: string | null
  project: { uuid: string, name: string, slug: string } | null
  subject_type: string | null
  subject_uuid: string | null
  created_at: string
}

export interface Evidence {
  type: 'log_line' | 'changed_file' | 'historical_failure' | 'metric' | 'config' | 'commit' | 'doc'
  content: string
  source_ref: string | null
  line_number: number | null
  related_failure_uuid?: string | null
  weight: number
}

export interface Analysis {
  uuid: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cached'
  confidence: number
  summary: string
  root_cause: string
  explanation: string | null
  is_transient: boolean
  retry_recommended: boolean
  classification_source: 'rules' | 'ml' | 'llm' | 'hybrid'
  classification_confidence: number
  used_rag: boolean
  similar_failures_count: number
  model_provider: string | null
  model_name: string | null
  latency_ms: number | null
  cost_usd: number
  cache_hit: boolean
  completed_at: string | null
  evidence: Evidence[]
  feedback: { given: boolean, was_helpful: boolean | null }
}

export interface FailureDetail {
  uuid: string
  status: string
  severity: Severity
  category: FailureCategory
  subcategory: string | null
  error_message: string | null
  stage_name: string | null
  job_name: string | null
  exit_code: number | null
  failed_at: string
  occurrence_index: number
  is_flaky: boolean
  is_transient: boolean
  project: { uuid: string, name: string, slug: string }
  pipeline: { uuid: string, iid: number, ref: string, commit_short_sha: string | null, commit_message: string | null, web_url: string | null }
  job: { uuid: string, name: string, duration_seconds: number | null, web_url: string | null } | null

  /** OBSERVED — facts. Rendered above and visually separate from `analysis`. */
  observed: {
    changed_files: ChangedFile[]
    previous_pipeline: { iid: number, status: PipelineStatus, finished_at: string } | null
    log_excerpt_url: string
  }

  /** INFERENCE — never merge with `observed`. */
  analysis: Analysis | null
  similar_failures: SimilarFailure[]
  recommendations: Recommendation[]
}
```

> **Keep `observed` and `analysis` as separate objects in the TypeScript type too.** If they share a shape, some component will eventually render them identically, and the distinction the whole trust model rests on quietly disappears.

```ts
// ready — src/types/api.contract.test.ts
// Guards against silent backend drift. Runs against the seeded API in CI.
import { expect, it } from 'vitest'

it('workspace summary matches the contract', async () => {
  const res = await fetch('http://localhost:8000/api/v1/workspace/summary', {
    headers: { Authorization: `Bearer ${process.env.TEST_TOKEN}` },
  })
  const { data } = await res.json()

  for (const key of ['projects', 'pipelines_today', 'failures_today', 'success_rate'])
    expect(data).toHaveProperty(key)

  expect(data.failures_today).toHaveProperty('positive_direction')
})
```

- [ ] Types written for every endpoint used
- [ ] Contract test runs in CI

---

## 11.5 API client

```ts
// ready — src/api/client.ts
import axios, { type AxiosError } from 'axios'
import NProgress from 'nprogress'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api/v1',
  withCredentials: true,
  headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
})

let inFlight = 0

api.interceptors.request.use((config) => {
  if (++inFlight === 1)
    NProgress.start()

  const auth = useAuthStore()
  if (auth.currentTeam)
    config.headers['X-Team'] = auth.currentTeam.uuid

  return config
})

export interface ApiError {
  message: string
  errorCode: string | null
  retryable: boolean
  status: number
  validation: Record<string, string[]> | null
}

api.interceptors.response.use(
  (res) => {
    if (--inFlight === 0)
      NProgress.done()
    return res
  },
  (error: AxiosError<any>) => {
    if (--inFlight === 0)
      NProgress.done()

    const status = error.response?.status ?? 0
    const body = error.response?.data ?? {}

    if (status === 401 && router.currentRoute.value.meta.requiresAuth) {
      useAuthStore().clear()
      router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
    }

    if (status === 419) {
      // Sanctum CSRF cookie expired — refresh it once and let the caller retry.
      return axios.get('/sanctum/csrf-cookie').then(() => Promise.reject(normalize(error)))
    }

    return Promise.reject(normalize(error))
  },
)

function normalize(error: AxiosError<any>): ApiError {
  const status = error.response?.status ?? 0
  const body = error.response?.data ?? {}

  return {
    message: body.message ?? (status === 0 ? 'Cannot reach the server.' : 'Something went wrong.'),
    errorCode: body.error_code ?? null,
    retryable: body.retryable ?? status >= 500,
    status,
    validation: status === 422 ? body.errors ?? null : null,
  }
}
```

```ts
// ready — src/api/queries/workspace.ts
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/api/client'
import type { ActivityItem, ProjectCard, WorkspaceSummary } from '@/types/api'

export function useWorkspaceSummary() {
  return useQuery({
    queryKey: ['workspace', 'summary'],
    queryFn: async () => (await api.get<{ data: WorkspaceSummary }>('/workspace/summary')).data.data,
    staleTime: 30_000,
    refetchInterval: 60_000,       // KPIs drift; refresh quietly in the background
  })
}

export function useWorkspaceProjects() {
  return useQuery({
    queryKey: ['workspace', 'projects'],
    queryFn: async () => (await api.get<{ data: ProjectCard[] }>('/workspace/projects')).data.data,
    staleTime: 30_000,
  })
}

export function useWorkspaceActivity(limit = 10) {
  return useQuery({
    queryKey: ['workspace', 'activity', limit],
    queryFn: async () =>
      (await api.get<{ data: ActivityItem[] }>('/workspace/activity', { params: { limit } })).data.data,
    staleTime: 15_000,
    refetchInterval: 30_000,
  })
}
```

**Polling policy** — realtime replaces most of this in file 17, but these are the fallbacks and they must be right:

| Data | Interval | Why |
|---|---|---|
| Workspace KPIs | 60 s | Slow-moving aggregates |
| Project overview | 60 s | Same |
| Pipeline list | 20 s **only if any pipeline is running** | Stop polling when nothing is in flight |
| Single running pipeline | 5 s | The user is watching it |
| Failure detail with `status = analyzing` | 3 s until terminal | The user is waiting for the analysis |
| Everything else | never | Refetch on window focus |

```ts
// ready — src/composables/usePolling.ts
import { computed, type Ref } from 'vue'

/** Poll only while a condition holds. Unconditional intervals are how a dashboard
 *  quietly becomes a load generator. */
export function useConditionalInterval(active: Ref<boolean>, ms: number) {
  return computed(() => (active.value ? ms : false as const))
}
```

- [ ] Client + interceptors written
- [ ] Query hooks for workspace, project, pipelines, failures
- [ ] Polling is conditional everywhere

---

## 11.6 Stores

```ts
// ready — src/stores/auth.ts
import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { AuthUser, TeamSummary } from '@/types/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as AuthUser | null,
    ready: false,
  }),

  getters: {
    isAuthenticated: s => s.user !== null,
    currentTeam: (s): TeamSummary | null => s.user?.current_team ?? null,
    role: s => s.user?.current_team?.role ?? null,
    permissions: s => s.user?.permissions ?? [],
    needsOnboarding: s => s.user !== null && !s.user.onboarded_at,
    initials: s => s.user?.initials ?? '',
  },

  actions: {
    /** Single source of truth for authorization in the UI. Never re-derive from role. */
    can(permission: string): boolean {
      return this.permissions.includes(permission)
    },

    async fetchUser() {
      try {
        this.user = (await api.get('/auth/me')).data.data
      }
      catch {
        this.user = null
      }
      finally {
        this.ready = true
      }
    },

    async login(email: string, password: string, remember = false) {
      await api.get('/sanctum/csrf-cookie', { baseURL: '/' })
      await api.post('/auth/login', { email, password, remember })
      await this.fetchUser()
    },

    async switchTeam(uuid: string) {
      await api.post(`/teams/${uuid}/switch`)
      await this.fetchUser()
      // Server state is team-scoped — everything cached is now wrong.
      window.location.reload()
    },

    clear() {
      this.user = null
    },
  },
})
```

```ts
// ready — src/stores/ui.ts
export const useUiStore = defineStore('ui', {
  state: () => ({
    sidebarCollapsed: useStorage('pm.sidebar', false),
    theme: useStorage<'dark' | 'light' | 'system'>('pm.theme', 'dark'),
    commandPaletteOpen: false,
    projectViewMode: useStorage<'grid' | 'list'>('pm.projectView', 'grid'),
  }),
  actions: {
    applyTheme() {
      const dark = this.theme === 'dark'
        || (this.theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
      document.documentElement.classList.toggle('dark', dark)
      document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    },
  },
})
```

- [ ] `auth`, `ui`, `notifications` stores written

---

## 11.7 Router

```ts
// ready — src/router/index.ts (shape)
const routes: RouteRecordRaw[] = [
  // public
  { path: '/', name: 'landing', component: LandingView, meta: { layout: 'public' } },
  { path: '/login', name: 'login', component: LoginView, meta: { layout: 'auth', guest: true } },
  { path: '/register', name: 'register', component: RegisterView, meta: { layout: 'auth', guest: true } },
  { path: '/forgot-password', name: 'forgot-password', component: ForgotPasswordView, meta: { layout: 'auth', guest: true } },
  { path: '/reset-password/:token', name: 'reset-password', component: ResetPasswordView, meta: { layout: 'auth', guest: true } },
  { path: '/invitations/:token', name: 'accept-invitation', component: AcceptInvitationView, meta: { layout: 'auth' } },

  // onboarding
  { path: '/welcome', name: 'onboarding', component: OnboardingView, meta: { requiresAuth: true, layout: 'blank' } },

  // workspace
  {
    path: '/app',
    meta: { requiresAuth: true, layout: 'workspace' },
    children: [
      { path: '', name: 'workspace', component: WorkspaceView },
      { path: 'projects', name: 'projects', component: ProjectsView },
      { path: 'activity', name: 'activity', component: ActivityView },
      { path: 'members', name: 'members', component: MembersView, meta: { permission: 'team.manage' } },
      { path: 'integrations', name: 'integrations', component: IntegrationsView, meta: { permission: 'projects.manage' } },
      { path: 'ai-providers', name: 'ai-providers', component: AiProvidersView, meta: { permission: 'projects.manage' } },
      { path: 'settings', name: 'workspace-settings', component: WorkspaceSettingsView },
    ],
  },

  // project
  {
    path: '/app/projects/:slug',
    meta: { requiresAuth: true, layout: 'project' },
    props: true,
    children: [
      { path: '', name: 'project.overview', component: ProjectOverviewView },
      { path: 'pipelines', name: 'project.pipelines', component: PipelinesView },
      { path: 'pipelines/:iid', name: 'project.pipeline', component: PipelineDetailView, props: true },
      { path: 'failures', name: 'project.failures', component: FailuresView },
      { path: 'failures/:uuid', name: 'project.failure', component: FailureDetailView, props: true },
      { path: 'analytics', name: 'project.analytics', component: AnalyticsView },
      { path: 'analyses', name: 'project.analyses', component: AnalysesView },
      { path: 'history', name: 'project.history', component: FailureHistoryView },
      { path: 'knowledge', name: 'project.knowledge', component: KnowledgeView },
      { path: 'remediation', name: 'project.remediation', component: RemediationView },
      { path: 'integration', name: 'project.integration', component: ProjectIntegrationView, meta: { permission: 'projects.manage' } },
      { path: 'settings', name: 'project.settings', component: ProjectSettingsView, meta: { permission: 'projects.manage' } },
    ],
  },

  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView, meta: { layout: 'blank' } },
]
```

```ts
// ready — src/router/guards.ts
router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.ready)
    await auth.fetchUser()

  if (to.meta.requiresAuth && !auth.isAuthenticated)
    return { name: 'login', query: { redirect: to.fullPath } }

  if (to.meta.guest && auth.isAuthenticated)
    return { name: 'workspace' }

  // Force onboarding once, but never trap the user in a loop.
  if (auth.isAuthenticated && auth.needsOnboarding && to.name !== 'onboarding')
    return { name: 'onboarding' }

  if (to.meta.permission && !auth.can(to.meta.permission as string))
    return { name: 'workspace' }

  return true
})
```

> **Nav guards are convenience, not security.** Every one of these routes is also enforced by a Laravel policy (file 04). A guard that is the *only* check is a client-side lock on a server-side door.

- [ ] Router + guards written
- [ ] Layouts resolved from `meta.layout`

---

## Definition of Done

```bash
npm run dev                 # boots at :5173
npm run build               # clean
npx vue-tsc --noEmit        # no type errors
```

- [ ] Login against the seeded backend works and lands on `/app`
- [ ] `/app` renders the workspace summary JSON on screen (unstyled is fine)
- [ ] Switching teams reloads with different data
- [ ] Logging out redirects to `/login`

**Next:** [`12-frontend-design-system.md`](12-frontend-design-system.md)
