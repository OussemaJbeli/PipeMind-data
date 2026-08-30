# 14 — Workspace Page

**Repo:** `PipeMind-front` · **Depends on:** 12 · **Milestone:** M2

The global workspace home. Target: [`../ui/workspace.png`](../ui/workspace.png) — build to match.

Data: `GET /workspace/summary`, `GET /workspace/projects`, `GET /workspace/activity` (file 04).

---

## 14.1 Layout

```text
┌─────────────┬────────────────────────────────────────────────────────────────┐
│ ◆ PipeMind  │                          [+ Add Project]  [🔔3]  [🌙]          │ 68px
├─────────────┼────────────────────────────────────────────────────────────────┤
│             │                                                                │
│ 🏠 Home  ◄  │  Good evening, Oussema                                         │
│ 📁 Projects │  Here's what's happening across your workspace.                 │
│ 📊 Activity │                                                                │
│ ─────────── │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│ 👥 Workspace│  │ ▣ PROJECTS│ │ ⚯ PIPELINES│ │ ! FAILURES│ │ ↗ SUCCESS │      │
│   Members   │  │    4      │ │   127     │ │    3      │ │  96.3%   │        │
│   Integr…   │  │ +1 week   │ │ +18.7%    │ │ -25%      │ │ +2.4%    │        │
│   AI Prov…  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│   Settings  │                                                                │
│             │  Your Projects   [🔍 Search…] [▦][☰]      Recent Activity  View all│
│             │  ┌──────────────────┐ ┌──────────────────┐  ┌──────────────┐   │
│             │  │ ▣ biker-api    ● │ │ ▣ biker-front  ● │  │ ! biker-api  │   │
│             │  │ Laravel•Docker…  │ │ Vue•TypeScript…  │  │   #821 failed│   │
│             │  │ ◐98% 2 fails 124 │ │ ◐94% 1 fail  87  │  ├──────────────┤   │
│             │  │ #821 ✓ 2min [Open│ │ #491 ✓ 10min[Open│  │ ✓ biker-front│   │
│             │  └──────────────────┘ └──────────────────┘  ├──────────────┤   │
│             │  ┌──────────────────┐ ┌──────────────────┐  │ ⚠ biker-mobil│   │
│             │  │ ▣ biker-mobile ● │ │ ▣ biker-admin  ● │  ├──────────────┤   │
│             │  └──────────────────┘ └──────────────────┘  │ ✦ AI Analysis│   │
│ ┌─────────┐ │  ┌───── + Add New Project ─────┐            │[View all act]│   │
│ │OU Oussema│ │  └─────────────────────────────┘            └──────────────┘   │
│ │   Admin ⌄│ │                                                                │
└─┴─────────┴─┴────────────────────────────────────────────────────────────────┘
   232px          main: 1fr                                     right: 350px
```

```vue
<!-- ready — src/views/workspace/WorkspaceView.vue -->
<script setup lang="ts">
const { data: summary, isLoading: loadingSummary, error: summaryError } = useWorkspaceSummary()
const { data: projects, isLoading: loadingProjects, refetch } = useWorkspaceProjects()
const { data: activity } = useWorkspaceActivity(10)

const ui = useUiStore()
const search = ref('')

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q)
    return projects.value ?? []

  return (projects.value ?? []).filter(p =>
    p.name.toLowerCase().includes(q)
    || p.tech_stack.some(t => t.toLowerCase().includes(q)),
  )
})
</script>

<template>
  <div class="mx-auto max-w-[1600px]">
    <WorkspaceGreeting />

    <KpiRow :summary="summary" :loading="loadingSummary" :error="summaryError" class="mt-6" />

    <div class="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1fr)_350px]">
      <section>
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-xl font-semibold">Your Projects</h2>

          <div class="flex items-center gap-2">
            <PmInput v-model="search" placeholder="Search projects…" icon="i-lucide-search" class="w-64" />
            <ViewModeToggle v-model="ui.projectViewMode" />
          </div>
        </div>

        <ProjectGrid
          v-if="ui.projectViewMode === 'grid'"
          :projects="filtered" :loading="loadingProjects" @refresh="refetch"
        />
        <ProjectTable v-else :projects="filtered" :loading="loadingProjects" />
      </section>

      <ActivityPanel :items="activity" title="Recent Activity" :to="{ name: 'activity' }" />
    </div>
  </div>
</template>
```

---

## 14.2 Greeting

```vue
<!-- ready — src/components/workspace/WorkspaceGreeting.vue -->
<script setup lang="ts">
const auth = useAuthStore()

// Time-of-day greeting in the USER's timezone, not the browser's. A distributed
// team should not be told "good evening" at 9am because the server is elsewhere.
const greeting = computed(() => {
  const tz = auth.user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
  const hour = Number(new Intl.DateTimeFormat('en', { hour: 'numeric', hour12: false, timeZone: tz })
    .format(new Date()))

  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
})
</script>

<template>
  <header>
    <h1 class="text-[26px] font-semibold leading-tight">
      {{ greeting }}, <span class="text-accent">{{ auth.user?.name?.split(' ')[0] }}</span>
    </h1>
    <p class="mt-1 text-sm text-dim">Here's what's happening across your workspace.</p>
  </header>
</template>
```

---

## 14.3 KPI tiles

```vue
<!-- ready — src/components/workspace/KpiTile.vue -->
<script setup lang="ts">
import { deltaTone } from '@/utils/format'
import type { Metric } from '@/types/api'

const props = defineProps<{
  label: string
  icon: string
  color: string
  metric: Metric | undefined
  loading?: boolean
}>()

const tone = computed(() => deltaTone(props.metric?.delta, props.metric?.positive_direction ?? 'up'))

const toneClass = computed(() => ({
  positive: 'text-accent',
  negative: 'text-[var(--pm-danger)]',
  neutral: 'text-dim',
}[tone.value]))
</script>

<template>
  <PmCard hoverable>
    <div v-if="loading" class="flex items-center gap-4">
      <PmSkeleton class="size-11 rounded-[var(--pm-radius)]" />
      <div class="flex-1 space-y-2">
        <PmSkeleton class="h-3 w-24" />
        <PmSkeleton class="h-7 w-16" />
      </div>
    </div>

    <div v-else class="flex items-start gap-4">
      <PmIconTile :icon="icon" :color="color" />

      <div class="min-w-0 flex-1">
        <p class="text-[11px] font-medium uppercase tracking-wider text-dim">{{ label }}</p>

        <p class="mt-1 text-[30px] font-semibold leading-none tnum">
          {{ metric?.display ?? metric?.value ?? '—' }}<span
            v-if="metric?.unit && !metric?.display"
            class="text-xl"
          >{{ metric.unit }}</span>
        </p>

        <p v-if="metric?.delta_label" class="mt-2 text-xs font-medium" :class="toneClass">
          {{ metric.delta_label }}
        </p>
      </div>
    </div>
  </PmCard>
</template>
```

```vue
<!-- ready — src/components/workspace/KpiRow.vue -->
<template>
  <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
    <KpiTile label="Projects" icon="i-lucide-box" color="var(--pm-accent)"
             :metric="summary?.projects" :loading="loading" />
    <KpiTile label="Pipelines today" icon="i-lucide-git-branch" color="var(--pm-accent)"
             :metric="summary?.pipelines_today" :loading="loading" />
    <KpiTile label="Failures today" icon="i-lucide-circle-alert" color="var(--pm-accent)"
             :metric="summary?.failures_today" :loading="loading" />
    <KpiTile label="Avg. success rate" icon="i-lucide-trending-up" color="var(--pm-accent)"
             :metric="summary?.success_rate" :loading="loading" />
  </div>
</template>
```

> **Icon tiles stay lime across all four**, matching the mockup — they read as a set. Status color belongs on the *delta*, which is where the meaning is. And because `positive_direction` comes from the server, "−25% failures" renders green without any component knowing what a failure is.

---

## 14.4 Project card

The densest component in the app. Every element in the mockup, in order.

```vue
<!-- ready — src/components/workspace/ProjectCard.vue -->
<script setup lang="ts">
import { duration } from '@/utils/format'
import { PIPELINE_STATUS_META } from '@/composables/useStatusMeta'
import type { ProjectCard as Project } from '@/types/api'

const props = defineProps<{ project: Project }>()

const HEALTH_DOT = {
  healthy:  'var(--pm-success)',
  degraded: 'var(--pm-warning)',
  failing:  'var(--pm-danger)',
  unknown:  'var(--pm-text-mute)',
} as const

const lastStatus = computed(() =>
  props.project.last_pipeline
    ? PIPELINE_STATUS_META[props.project.last_pipeline.status]
    : null)

const lastRelative = useRelativeTime(() => props.project.last_pipeline?.finished_at)
</script>

<template>
  <PmCard hoverable padded={false} class="group flex flex-col">
    <!-- header -->
    <div class="flex items-start gap-3 p-4 pb-3">
      <PmIconTile :icon="`i-lucide-${project.icon}`" :color="project.color" />

      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <h3 class="truncate text-[15px] font-semibold">{{ project.name }}</h3>
          <PmTooltip :content="`Health: ${project.health_status}`">
            <span
              class="size-2 shrink-0 rounded-full"
              :style="{ background: HEALTH_DOT[project.health_status] }"
              :aria-label="`Health: ${project.health_status}`"
            />
          </PmTooltip>
        </div>
        <p class="mt-0.5 truncate text-xs text-dim">{{ project.tech_stack.join(' · ') }}</p>
      </div>

      <ProjectCardMenu :project="project" />
    </div>

    <!-- metrics -->
    <div class="grid grid-cols-[auto_1fr_1fr_1fr] items-center gap-3 px-4 pb-4">
      <PmRadialGauge :value="project.success_rate" :size="54" />

      <div>
        <p class="text-[15px] font-semibold tnum">{{ project.success_rate.toFixed(0) }}%</p>
        <p class="text-[11px] text-dim">Success rate</p>
      </div>

      <div>
        <p
          class="text-[15px] font-semibold tnum"
          :class="project.failures_today > 0 ? 'text-[var(--pm-danger)]' : 'text-fg'"
        >
          {{ project.failures_today }}
        </p>
        <p class="text-[11px] text-dim">Failures today</p>
      </div>

      <div>
        <p class="text-[15px] font-semibold tnum">{{ project.pipelines_count }}</p>
        <p class="text-[11px] text-dim">Pipelines</p>
      </div>
    </div>

    <!-- footer -->
    <div class="mt-auto flex items-center justify-between gap-3 border-t px-4 py-3">
      <p class="flex min-w-0 items-center gap-1.5 truncate text-xs text-dim">
        <template v-if="project.last_pipeline">
          Last pipeline:
          <span class="font-medium text-fg">#{{ project.last_pipeline.iid }}</span>
          <span class="inline-flex items-center gap-1" :style="{ color: lastStatus!.color }">
            <i :class="lastStatus!.icon" class="size-3" />{{ lastStatus!.label }}
          </span>
          <span class="text-mute">{{ lastRelative }}</span>
        </template>
        <template v-else>No pipelines yet</template>
      </p>

      <PmButton
        variant="outline" size="sm"
        @click="$router.push({ name: 'project.overview', params: { slug: project.slug } })"
      >
        Open Project <i-lucide-chevron-right class="size-3.5" />
      </PmButton>
    </div>
  </PmCard>
</template>
```

**Detail decisions:**

| Element | Choice | Why |
|---|---|---|
| Health dot | Separate from success rate | Success rate is a 30-day average; the dot is *right now*. A project at 98% whose last pipeline just failed must not look green. |
| Failures today | Red only when > 0 | A red `0` trains people to ignore red. |
| Radial ring color | Threshold-based, not fixed lime | The ring is scannable without reading — the grid's health is legible at a glance. |
| Relative time | Live-ticking composable | A static "2 min ago" that stays "2 min ago" for an hour is actively misleading on a monitoring tool. |
| Card is not a link | Explicit "Open Project" button | The card contains a menu and a tooltip; nesting interactive elements inside an anchor breaks keyboard navigation. |

```vue
<!-- ready — src/components/workspace/ProjectGrid.vue -->
<template>
  <div class="grid gap-4 md:grid-cols-2">
    <template v-if="loading">
      <ProjectCardSkeleton v-for="i in 4" :key="i" />
    </template>

    <template v-else-if="projects.length">
      <ProjectCard v-for="p in projects" :key="p.uuid" :project="p" />
    </template>

    <PmEmptyState
      v-else class="md:col-span-2"
      icon="i-lucide-folder-open"
      title="No projects yet"
      message="Connect a CI/CD platform and import a repository to start monitoring."
    >
      <PmButton variant="primary" @click="$router.push({ name: 'integrations' })">
        Connect CI/CD
      </PmButton>
    </PmEmptyState>

    <!-- Add-new tile, always last -->
    <button
      v-if="projects.length && auth.can('projects.manage')"
      class="grid min-h-[180px] place-items-center rounded-[var(--pm-radius-lg)] border border-dashed
             text-dim transition-colors hover:border-[color:var(--pm-accent)]/50 hover:text-accent md:col-span-2"
      @click="addProject"
    >
      <span class="flex items-center gap-2 text-sm font-medium">
        <i-lucide-plus class="size-4" /> Add New Project
      </span>
    </button>
  </div>
</template>
```

- [ ] `ProjectCard`, `ProjectGrid`, `ProjectTable`, `ProjectCardSkeleton`, `ProjectCardMenu` built
- [ ] Grid/list toggle persists in `localStorage`

---

## 14.5 Activity panel

```vue
<!-- ready — src/components/workspace/ActivityItem.vue -->
<script setup lang="ts">
import type { ActivityItem } from '@/types/api'

const props = defineProps<{ item: ActivityItem }>()

// The fixed action vocabulary from file 02. Unknown actions degrade to a neutral dot
// rather than throwing — the backend can add actions without breaking the UI.
const ACTION_META: Record<string, { icon: string, color: string }> = {
  'pipeline.failed':        { icon: 'i-lucide-circle-alert',   color: 'var(--pm-danger)' },
  'pipeline.succeeded':     { icon: 'i-lucide-circle-check',   color: 'var(--pm-success)' },
  'pipeline.started':       { icon: 'i-lucide-play',           color: 'var(--pm-running)' },
  'job.failed':             { icon: 'i-lucide-triangle-alert', color: 'var(--pm-warning)' },
  'failure.detected':       { icon: 'i-lucide-triangle-alert', color: 'var(--pm-danger)' },
  'failure.resolved':       { icon: 'i-lucide-circle-check',   color: 'var(--pm-success)' },
  'analysis.completed':     { icon: 'i-lucide-sparkles',       color: 'var(--pm-ai)' },
  'anomaly.detected':       { icon: 'i-lucide-activity',       color: 'var(--pm-warning)' },
  'remediation.approved':   { icon: 'i-lucide-shield-check',   color: 'var(--pm-accent)' },
  'integration.error':      { icon: 'i-lucide-plug-zap',       color: 'var(--pm-danger)' },
}

const meta = computed(() =>
  ACTION_META[props.item.action] ?? { icon: 'i-lucide-circle', color: 'var(--pm-text-mute)' })

const time = useRelativeTime(() => props.item.created_at)
const to = computed(() => activityRoute(props.item))   // maps subject_type + uuid → route
</script>

<template>
  <component
    :is="to ? 'RouterLink' : 'div'" :to="to"
    class="flex gap-3 px-4 py-3 transition-colors"
    :class="to && 'hover:bg-surface-2'"
  >
    <span
      class="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full border"
      :style="{ borderColor: `color-mix(in srgb, ${meta.color} 35%, transparent)`,
                background: `color-mix(in srgb, ${meta.color} 10%, transparent)` }"
    >
      <i :class="meta.icon" class="size-4" :style="{ color: meta.color }" />
    </span>

    <div class="min-w-0 flex-1">
      <div class="flex items-baseline justify-between gap-2">
        <p class="truncate text-[13px] font-medium">{{ item.title }}</p>
        <time class="shrink-0 text-[11px] text-mute" :datetime="item.created_at">{{ time }}</time>
      </div>
      <p v-if="item.description" class="mt-0.5 line-clamp-2 text-xs text-dim">
        {{ item.description }}
      </p>
    </div>
  </component>
</template>
```

```vue
<!-- ready — src/components/workspace/ActivityPanel.vue -->
<template>
  <PmCard :padded="false" class="self-start">
    <div class="flex items-center justify-between px-4 pb-3 pt-4">
      <h3 class="text-[15px] font-semibold">{{ title }}</h3>
      <RouterLink :to="to" class="text-xs font-medium text-accent hover:underline">View all</RouterLink>
    </div>

    <div class="divide-y">
      <template v-if="items?.length">
        <ActivityItem v-for="i in items" :key="i.uuid" :item="i" />
      </template>
      <ActivitySkeleton v-else-if="items === undefined" :count="5" />
      <p v-else class="px-4 py-8 text-center text-sm text-dim">No activity yet.</p>
    </div>

    <div class="p-3">
      <PmButton variant="outline" block size="sm" @click="$router.push(to)">
        View all activity
      </PmButton>
    </div>
  </PmCard>
</template>
```

- [ ] Activity components built
- [ ] Every activity type routes to the right destination
- [ ] Unknown actions render neutrally instead of crashing

---

## 14.6 Topbar & sidebar

```vue
<!-- ready — src/components/layout/WorkspaceTopbar.vue -->
<template>
  <div class="flex flex-1 items-center justify-end gap-3">
    <PmButton
      v-if="auth.can('projects.manage')" variant="primary"
      @click="addProject"
    >
      <i-lucide-plus class="size-4" /> Add Project
    </PmButton>

    <NotificationBell />
    <ThemeToggle />
  </div>
</template>
```

```vue
<!-- ready — src/components/layout/NotificationBell.vue -->
<script setup lang="ts">
const { data: count } = useNotificationCount()   // polls /notifications/count every 30s
const open = ref(false)
</script>

<template>
  <PmDropdown v-model:open="open" align="end" :width="380">
    <template #trigger>
      <button
        class="relative grid size-10 place-items-center rounded-[var(--pm-radius)]
               text-dim transition-colors hover:bg-surface-2 hover:text-fg"
        :aria-label="`Notifications${count ? `, ${count} unread` : ''}`"
      >
        <i-lucide-bell class="size-5" />
        <span
          v-if="count"
          class="absolute -right-0.5 -top-0.5 grid min-w-[18px] place-items-center rounded-full
                 bg-[var(--pm-danger)] px-1 text-[10px] font-semibold text-white"
        >{{ count > 99 ? '99+' : count }}</span>
      </button>
    </template>

    <NotificationList @close="open = false" />
  </PmDropdown>
</template>
```

**Workspace sidebar groups:**

```ts
// ready
const workspaceNav: NavGroup[] = [
  { items: [
    { label: 'Home',     icon: 'i-lucide-house',         to: { name: 'workspace' } },
    { label: 'Projects', icon: 'i-lucide-folder',        to: { name: 'projects' } },
    { label: 'Activity', icon: 'i-lucide-activity',      to: { name: 'activity' } },
  ] },
  { label: 'Workspace', items: [
    { label: 'Members',      icon: 'i-lucide-users',     to: { name: 'members' },  permission: 'team.manage' },
    { label: 'Integrations', icon: 'i-lucide-plug',      to: { name: 'integrations' }, permission: 'projects.manage' },
    { label: 'AI Providers', icon: 'i-lucide-sparkles',  to: { name: 'ai-providers' }, permission: 'projects.manage' },
    { label: 'Settings',     icon: 'i-lucide-settings',  to: { name: 'workspace-settings' } },
  ] },
]
```

The user card sits at the bottom of the sidebar with a dropdown: profile, team switcher, theme, sign out.

- [ ] Topbar, bell, theme toggle, user menu built
- [ ] Sidebar matches the mockup grouping

---

## 14.7 Supporting views

| Route | View | Notes |
|---|---|---|
| `/app/projects` | `ProjectsView` | Full list, filter by provider/health/tech, sortable table |
| `/app/activity` | `ActivityView` | Infinite scroll, filter by action type / project / level |
| `/app/members` | `MembersView` | Table + role editor + invite modal + pending invitations |
| `/app/integrations` | `IntegrationsView` | Cards per integration, status, last event, webhook URL, test/sync |
| `/app/ai-providers` | `AiProvidersView` | Provider list, test button, default toggle, **usage + budget bar** |
| `/app/settings` | `WorkspaceSettingsView` | Name, logo, timezone, privacy mode, budget, danger zone |

**The AI Providers page carries the budget widget** — spend to date, monthly ceiling, projected month-end, cache hit rate, cost by model. It is the page where "why is this expensive" gets answered, so put the numbers there rather than burying them in settings.

```text
┌────────────────────────────────────────────────┐
│  AI usage — August 2026                        │
│                                                │
│  $4.82 of $25.00                               │
│  ████████░░░░░░░░░░░░░░░░░░░░  19%             │
│                                                │
│  Analyses      312      Cache hits      41%    │
│  Avg cost      $0.0154  Avg latency   3.8s     │
│  Projected month-end          $7.10            │
└────────────────────────────────────────────────┘
```

- [ ] Six supporting views built

---

## Definition of Done

- [ ] The workspace page is **visually indistinguishable from `ui/workspace.png`** at 1536×1024
- [ ] Loading skeletons match the final layout — no reflow when data lands
- [ ] Empty state (new workspace, zero projects) is designed, not broken
- [ ] Error state when the API is down shows a retry, not a blank page
- [ ] Responsive: 4→2→1 KPI columns, 2→1 project columns, activity moves below at < 1280px
- [ ] Light theme correct
- [ ] Keyboard: tab through KPIs → search → cards → activity, visible focus throughout
- [ ] No layout shift when relative times tick

**Next:** [`15-frontend-project.md`](15-frontend-project.md)
