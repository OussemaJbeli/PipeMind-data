# 12 — Frontend Design System

**Repo:** `PipeMind-front` · **Depends on:** 11 · **Milestone:** M1

Tokens, base components, charts and status metadata. Everything in files 13–16 is assembled from this file — build it properly once and the pages become composition rather than CSS.

Reference: [`../ui/workspace.png`](../ui/workspace.png) and [`../ui/project.png`](../ui/project.png).

---

## 12.1 Tokens

```css
/* ready — src/assets/tokens.css */
:root {
  /* surfaces */
  --pm-bg:          #0A0B0E;
  --pm-sidebar:     #0C0E12;
  --pm-surface:     #101318;
  --pm-surface-2:   #161A21;
  --pm-surface-3:   #1C212A;
  --pm-border:      #1F242C;
  --pm-border-soft: #171B22;

  /* text */
  --pm-text:        #E7EAF0;
  --pm-text-dim:    #8B93A1;
  --pm-text-mute:   #5C6472;

  /* brand */
  --pm-accent:      #A9E831;
  --pm-accent-hi:   #C6F55A;
  --pm-accent-lo:   #7DB520;
  --pm-accent-dim:  rgb(169 232 49 / 12%);
  --pm-accent-glow: rgb(169 232 49 / 22%);

  /* status */
  --pm-success:     #4ADE80;
  --pm-danger:      #F04438;
  --pm-warning:     #F5A524;
  --pm-running:     #6366F1;
  --pm-ai:          #A855F7;
  --pm-info:        #38BDF8;

  /* radii + shadow */
  --pm-radius-sm:   8px;
  --pm-radius:      12px;
  --pm-radius-lg:   16px;
  --pm-radius-xl:   20px;
  --pm-shadow:      0 1px 2px rgb(0 0 0 / 40%);
  --pm-shadow-lg:   0 8px 32px rgb(0 0 0 / 45%);

  /* layout */
  --pm-sidebar-w:   232px;
  --pm-sidebar-w-collapsed: 68px;
  --pm-topbar-h:    68px;

  --pm-font:        'Inter', system-ui, -apple-system, sans-serif;
  --pm-font-mono:   'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
}

/* Light theme is a genuine second design, not an inversion.
   PipeMind is a dark-first developer tool; light mode must still feel deliberate. */
:root[data-theme='light'] {
  --pm-bg:          #F7F8FA;
  --pm-sidebar:     #FFFFFF;
  --pm-surface:     #FFFFFF;
  --pm-surface-2:   #F2F4F7;
  --pm-surface-3:   #E9ECF1;
  --pm-border:      #E3E7ED;
  --pm-border-soft: #EEF1F5;
  --pm-text:        #10141B;
  --pm-text-dim:    #5C6472;
  --pm-text-mute:   #8B93A1;
  --pm-accent:      #6FA80F;   /* darkened: #A9E831 on white fails contrast */
  --pm-accent-hi:   #5C8F0B;
  --pm-accent-dim:  rgb(111 168 15 / 10%);
  --pm-shadow:      0 1px 2px rgb(16 20 27 / 6%);
  --pm-shadow-lg:   0 8px 32px rgb(16 20 27 / 10%);
}
```

> **The lime accent must change in light mode.** `#A9E831` on white is roughly 1.6:1 — unreadable. Darkening it to `#6FA80F` keeps the brand recognisable and reaches AA. Any component hardcoding the hex instead of the token will break in light mode; use `var(--pm-accent)` everywhere.

```css
/* ready — src/assets/main.css */
@import 'tailwindcss';
@import './tokens.css';

@theme {
  --color-bg:        var(--pm-bg);
  --color-sidebar:   var(--pm-sidebar);
  --color-surface:   var(--pm-surface);
  --color-surface-2: var(--pm-surface-2);
  --color-surface-3: var(--pm-surface-3);
  --color-border:    var(--pm-border);
  --color-fg:        var(--pm-text);
  --color-dim:       var(--pm-text-dim);
  --color-mute:      var(--pm-text-mute);
  --color-accent:    var(--pm-accent);
  --color-success:   var(--pm-success);
  --color-danger:    var(--pm-danger);
  --color-warning:   var(--pm-warning);
  --color-running:   var(--pm-running);
  --color-ai:        var(--pm-ai);

  --radius-card: var(--pm-radius-lg);
  --font-sans:   var(--pm-font);
  --font-mono:   var(--pm-font-mono);
}

@layer base {
  * { border-color: var(--pm-border); }

  body {
    background: var(--pm-bg);
    color: var(--pm-text);
    font-family: var(--pm-font);
    font-feature-settings: 'cv02','cv03','cv04','tnum';
    -webkit-font-smoothing: antialiased;
  }

  /* Tabular numerals so metrics don't jitter as they update. */
  .tnum { font-variant-numeric: tabular-nums; }

  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb {
    background: var(--pm-surface-3);
    border-radius: 6px;
    border: 2px solid var(--pm-bg);
  }
  ::-webkit-scrollbar-thumb:hover { background: var(--pm-text-mute); }

  :focus-visible {
    outline: 2px solid var(--pm-accent);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
    }
  }
}
```

Fonts: self-host Inter and JetBrains Mono via `@fontsource` rather than a CDN — one less third party, and no layout shift.

- [ ] `tokens.css` + `main.css` written
- [ ] Theme toggle switches `data-theme` and every color follows

---

## 12.2 Status & category metadata

One source of truth for every status colour, icon and label. No component may switch on a status string itself.

```ts
// ready — src/composables/useStatusMeta.ts
import type { Component } from 'vue'
import type { PipelineStatus, Severity } from '@/types/domain'

export interface StatusMeta {
  label: string
  color: string        // CSS var reference
  bg: string
  icon: string         // iconify name
  pulse?: boolean
}

export const PIPELINE_STATUS_META: Record<PipelineStatus, StatusMeta> = {
  success:  { label: 'Success',  color: 'var(--pm-success)', bg: 'rgb(74 222 128 / 12%)',  icon: 'lucide:check' },
  failed:   { label: 'Failed',   color: 'var(--pm-danger)',  bg: 'rgb(240 68 56 / 12%)',   icon: 'lucide:triangle-alert' },
  running:  { label: 'Running',  color: 'var(--pm-running)', bg: 'rgb(99 102 241 / 12%)',  icon: 'lucide:loader-circle', pulse: true },
  queued:   { label: 'Queued',   color: 'var(--pm-text-dim)',bg: 'rgb(139 147 161 / 12%)', icon: 'lucide:clock' },
  canceled: { label: 'Canceled', color: 'var(--pm-text-mute)',bg: 'rgb(92 100 114 / 12%)', icon: 'lucide:circle-slash' },
  skipped:  { label: 'Skipped',  color: 'var(--pm-text-mute)',bg: 'rgb(92 100 114 / 12%)', icon: 'lucide:skip-forward' },
  manual:   { label: 'Manual',   color: 'var(--pm-warning)', bg: 'rgb(245 165 36 / 12%)',  icon: 'lucide:hand' },
  timeout:  { label: 'Timeout',  color: 'var(--pm-warning)', bg: 'rgb(245 165 36 / 12%)',  icon: 'lucide:timer-off' },
}

export const SEVERITY_META: Record<Severity, StatusMeta> = {
  low:      { label: 'Low',      color: 'var(--pm-text-dim)', bg: 'rgb(139 147 161 / 12%)', icon: 'lucide:info' },
  medium:   { label: 'Medium',   color: 'var(--pm-warning)',  bg: 'rgb(245 165 36 / 12%)',  icon: 'lucide:alert-circle' },
  high:     { label: 'High',     color: 'var(--pm-danger)',   bg: 'rgb(240 68 56 / 12%)',   icon: 'lucide:alert-triangle' },
  critical: { label: 'Critical', color: '#FF4D4D',            bg: 'rgb(255 77 77 / 18%)',   icon: 'lucide:octagon-alert' },
}

export function useStatusMeta(status: MaybeRef<PipelineStatus>) {
  return computed(() => PIPELINE_STATUS_META[unref(status)] ?? PIPELINE_STATUS_META.queued)
}
```

```ts
// ready — src/composables/useCategoryMeta.ts
// Colors MUST match App\Enums\FailureCategory::color() in the backend.
// The donut, the bar list and the pills all read from here, so they can never disagree.
export const CATEGORY_META: Record<FailureCategory, { label: string, color: string, icon: string }> = {
  DATABASE:       { label: 'Database',       color: '#A9E831', icon: 'lucide:database' },
  TEST:           { label: 'Tests',          color: '#F04438', icon: 'lucide:flask-conical' },
  DEPENDENCY:     { label: 'Dependencies',   color: '#F5A524', icon: 'lucide:package' },
  DOCKER:         { label: 'Docker',         color: '#38BDF8', icon: 'simple-icons:docker' },
  NETWORK:        { label: 'Network',        color: '#6366F1', icon: 'lucide:wifi-off' },
  BUILD:          { label: 'Build',          color: '#EC4899', icon: 'lucide:hammer' },
  DEPLOYMENT:     { label: 'Deployment',     color: '#14B8A6', icon: 'lucide:rocket' },
  CONFIGURATION:  { label: 'Configuration',  color: '#A855F7', icon: 'lucide:settings-2' },
  AUTHENTICATION: { label: 'Authentication', color: '#F97316', icon: 'lucide:key-round' },
  PERMISSION:     { label: 'Permission',     color: '#8B5CF6', icon: 'lucide:lock' },
  INFRASTRUCTURE: { label: 'Infrastructure', color: '#0EA5E9', icon: 'lucide:server' },
  RESOURCE:       { label: 'Resource',       color: '#EAB308', icon: 'lucide:cpu' },
  UNKNOWN:        { label: 'Unknown',        color: '#5C6472', icon: 'lucide:help-circle' },
}
```

- [ ] Both metadata modules written
- [ ] A test asserts the category colors match the backend enum (fetch `/v1/meta/categories`)

---

## 12.3 Base components

### PmCard

```vue
<!-- ready — src/components/ui/PmCard.vue -->
<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  subtitle?: string
  padded?: boolean
  hoverable?: boolean
  glow?: boolean          // the AI Insight treatment
}>(), { padded: true })
</script>

<template>
  <section
    class="relative rounded-[var(--pm-radius-lg)] border bg-surface transition-colors"
    :class="[
      hoverable && 'hover:border-[var(--pm-text-mute)] hover:bg-surface-2',
      glow && 'border-[color:var(--pm-accent)]/35 shadow-[0_0_28px_var(--pm-accent-glow)]',
    ]"
  >
    <header v-if="title || $slots.header" class="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
      <div class="min-w-0">
        <h3 v-if="title" class="truncate text-[15px] font-semibold text-fg">{{ title }}</h3>
        <p v-if="subtitle" class="mt-0.5 truncate text-xs text-dim">{{ subtitle }}</p>
      </div>
      <slot name="actions" />
    </header>

    <div :class="padded ? 'px-5 pb-5' : ''">
      <slot />
    </div>
  </section>
</template>
```

### PmButton

```vue
<!-- ready — src/components/ui/PmButton.vue -->
<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  block?: boolean
}>(), { variant: 'secondary', size: 'md' })
</script>

<template>
  <button
    class="inline-flex items-center justify-center gap-2 rounded-[var(--pm-radius)] font-medium
           transition-all disabled:cursor-not-allowed disabled:opacity-45"
    :class="[
      block && 'w-full',
      {
        sm: 'h-8 px-3 text-[13px]',
        md: 'h-10 px-4 text-sm',
        lg: 'h-12 px-6 text-[15px]',
      }[size],
      {
        primary:   'bg-accent text-[#0A0B0E] hover:bg-[var(--pm-accent-hi)] font-semibold',
        secondary: 'bg-surface-2 text-fg border border-[var(--pm-border)] hover:bg-surface-3',
        ghost:     'text-dim hover:text-fg hover:bg-surface-2',
        outline:   'border border-[color:var(--pm-accent)]/40 text-accent hover:bg-[var(--pm-accent-dim)]',
        danger:    'bg-[color:var(--pm-danger)]/12 text-[var(--pm-danger)] border border-[color:var(--pm-danger)]/30 hover:bg-[color:var(--pm-danger)]/20',
      }[variant],
    ]"
    :disabled="disabled || loading"
  >
    <i-lucide-loader-circle v-if="loading" class="size-4 animate-spin" />
    <slot />
  </button>
</template>
```

### PmStatusPill

```vue
<!-- ready — src/components/ui/PmStatusPill.vue -->
<script setup lang="ts">
import { PIPELINE_STATUS_META } from '@/composables/useStatusMeta'
import type { PipelineStatus } from '@/types/domain'

const props = defineProps<{ status: PipelineStatus, size?: 'sm' | 'md' }>()
const meta = computed(() => PIPELINE_STATUS_META[props.status])
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-md font-medium"
    :class="size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'"
    :style="{ color: meta.color, background: meta.bg }"
  >
    <i :class="[meta.icon, meta.pulse && 'animate-spin']" class="size-3" />
    {{ meta.label }}
  </span>
</template>
```

Also build: `PmBadge`, `PmInput`, `PmSelect`, `PmModal`, `PmDrawer`, `PmTooltip`, `PmDropdown`, `PmTabs`, `PmSkeleton`, `PmEmptyState`, `PmErrorState`, `PmAvatar`, `PmIconTile`, `PmProgressBar`, `PmToggle`, `PmConfirmDialog`.

### PmIconTile — the rounded icon square on every KPI card

```vue
<!-- ready — src/components/ui/PmIconTile.vue -->
<script setup lang="ts">
withDefaults(defineProps<{
  icon: string
  color?: string
  size?: 'sm' | 'md' | 'lg'
}>(), { color: 'var(--pm-accent)', size: 'md' })
</script>

<template>
  <div
    class="grid shrink-0 place-items-center rounded-[var(--pm-radius)]"
    :class="{ sm: 'size-8', md: 'size-11', lg: 'size-14' }[size]"
    :style="{ background: `color-mix(in srgb, ${color} 12%, transparent)` }"
  >
    <i :class="icon" class="size-5" :style="{ color }" />
  </div>
</template>
```

### Loading, empty and error states are components, not afterthoughts

```vue
<!-- ready — src/components/ui/PmAsyncBoundary.vue -->
<script setup lang="ts">
import type { ApiError } from '@/api/client'

defineProps<{
  loading: boolean
  error: ApiError | null
  empty?: boolean
  emptyTitle?: string
  emptyMessage?: string
}>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <PmSkeleton v-if="loading" />

  <!-- Distinguish "we can't reach the server" from "your pipeline failed".
       Conflating them is the single most confusing thing a monitoring UI can do. -->
  <PmErrorState
    v-else-if="error"
    :title="error.errorCode === 'AI_SERVICE_UNAVAILABLE' ? 'Analysis service unavailable' : 'Could not load'"
    :message="error.message"
    :retryable="error.retryable"
    @retry="$emit('retry')"
  />

  <PmEmptyState v-else-if="empty" :title="emptyTitle" :message="emptyMessage">
    <slot name="empty-action" />
  </PmEmptyState>

  <slot v-else />
</template>
```

- [ ] 18 base components built
- [ ] Every one renders correctly in both themes

---

## 12.4 Charts

Chart.js configured once with a shared dark theme. No component may pass raw Chart.js options.

```ts
// ready — src/components/charts/chartDefaults.ts
import { Chart } from 'chart.js/auto'

export function applyChartDefaults() {
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif'
  Chart.defaults.font.size = 11
  Chart.defaults.color = 'var(--pm-text-mute)'
  Chart.defaults.borderColor = 'var(--pm-border)'
  Chart.defaults.plugins.legend.display = false     // legends are rendered in Vue, not canvas
  Chart.defaults.plugins.tooltip = {
    ...Chart.defaults.plugins.tooltip,
    backgroundColor: '#161A21',
    borderColor: '#1F242C',
    borderWidth: 1,
    padding: 10,
    cornerRadius: 8,
    titleColor: '#E7EAF0',
    bodyColor: '#8B93A1',
    displayColors: true,
    boxPadding: 4,
  }
  Chart.defaults.animation = { duration: 300, easing: 'easeOutQuart' }
  Chart.defaults.maintainAspectRatio = false
}

export const AXIS = {
  grid: { color: 'rgba(31,36,44,0.6)', drawTicks: false },
  border: { display: false },
  ticks: { padding: 8, maxRotation: 0, autoSkipPadding: 20 },
}
```

> **Render legends in Vue, not on the canvas.** The mockup's legends have colored dots, labels, percentages and counts, and the Failure Breakdown legend rows are clickable filters. Canvas legends can't do any of that, and they don't inherit your theme tokens.

### Sparkline — on all five project KPI tiles

```vue
<!-- ready — src/components/charts/PmSparkline.vue -->
<script setup lang="ts">
import { Line } from 'vue-chartjs'

const props = withDefaults(defineProps<{
  data: number[]
  color?: string
  type?: 'line' | 'bar'
  height?: number
  fill?: boolean
}>(), { color: 'var(--pm-accent)', type: 'line', height: 40, fill: true })

const chartData = computed(() => ({
  labels: props.data.map((_, i) => i),
  datasets: [{
    data: props.data,
    borderColor: props.color,
    borderWidth: 1.5,
    tension: 0.35,
    pointRadius: 0,
    fill: props.fill,
    backgroundColor: (ctx: any) => {
      const { chart } = ctx
      if (!chart.chartArea)
        return 'transparent'
      const g = chart.ctx.createLinearGradient(0, chart.chartArea.top, 0, chart.chartArea.bottom)
      g.addColorStop(0, `color-mix(in srgb, ${props.color} 28%, transparent)`)
      g.addColorStop(1, 'transparent')
      return g
    },
  }],
}))

// A sparkline is a shape, not a readable chart. Strip every affordance.
const options = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false }, tooltip: { enabled: false } },
  scales: { x: { display: false }, y: { display: false } },
  elements: { point: { radius: 0 } },
}
</script>

<template>
  <div :style="{ height: `${height}px` }" aria-hidden="true">
    <Line :data="chartData" :options="options" />
  </div>
</template>
```

### RadialGauge — the success-rate ring on the workspace project cards

```vue
<!-- ready — src/components/charts/PmRadialGauge.vue -->
<script setup lang="ts">
const props = withDefaults(defineProps<{
  value: number          // 0–100
  size?: number
  thickness?: number
  color?: string
}>(), { size: 56, thickness: 5 })

const radius = computed(() => (props.size - props.thickness) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const offset = computed(() => circumference.value * (1 - Math.min(100, Math.max(0, props.value)) / 100))

// Color encodes health so the ring is readable without reading the number.
const stroke = computed(() =>
  props.color
  ?? (props.value >= 95 ? 'var(--pm-accent)'
    : props.value >= 85 ? 'var(--pm-warning)'
      : 'var(--pm-danger)'))
</script>

<template>
  <div class="relative grid place-items-center" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg :width="size" :height="size" class="-rotate-90">
      <circle
        :cx="size / 2" :cy="size / 2" :r="radius"
        fill="none" stroke="var(--pm-surface-3)" :stroke-width="thickness"
      />
      <circle
        :cx="size / 2" :cy="size / 2" :r="radius"
        fill="none" :stroke="stroke" :stroke-width="thickness" stroke-linecap="round"
        :stroke-dasharray="circumference" :stroke-dashoffset="offset"
        class="transition-[stroke-dashoffset] duration-500"
      />
    </svg>
    <span class="absolute text-[11px] font-semibold tnum" :style="{ color: stroke }">
      {{ Math.round(value) }}%
    </span>
  </div>
</template>
```

Also build:

| Component | Used by | Notes |
|---|---|---|
| `PmLineChart` | Pipeline Activity | multi-series, Vue legend, shared crosshair tooltip |
| `PmBarChart` | Pipeline Success Rate | per-bar color by threshold, 0/50/100 axis |
| `PmDonutChart` | Failure Breakdown | 68% cutout, center slot for "3 / Total" |
| `PmCategoryBars` | Most Common Failure Categories | icon + label + track + count + % |
| `PmHeatmap` | Analytics (file 19) | day × hour failure density |

- [ ] Charts built and theme-aware
- [ ] All charts re-render correctly on theme switch (watch `data-theme`)
- [ ] `aria-hidden` on decorative charts; data tables available behind a toggle for the meaningful ones

---

## 12.5 Layout shell

Two shells: **workspace** (`ui/workspace.png`) and **project** (`ui/project.png`). They share `AppShell`; the sidebar content differs.

```vue
<!-- ready — src/components/layout/AppShell.vue -->
<script setup lang="ts">
const ui = useUiStore()
</script>

<template>
  <div class="min-h-screen bg-bg">
    <aside
      class="fixed inset-y-0 left-0 z-40 flex flex-col border-r bg-sidebar transition-[width] duration-200"
      :style="{ width: ui.sidebarCollapsed ? 'var(--pm-sidebar-w-collapsed)' : 'var(--pm-sidebar-w)' }"
    >
      <slot name="sidebar" />
    </aside>

    <div
      class="flex min-h-screen flex-col transition-[padding] duration-200"
      :style="{ paddingLeft: ui.sidebarCollapsed ? 'var(--pm-sidebar-w-collapsed)' : 'var(--pm-sidebar-w)' }"
    >
      <header
        class="sticky top-0 z-30 flex items-center gap-4 border-b bg-bg/85 px-6 backdrop-blur-md"
        :style="{ height: 'var(--pm-topbar-h)' }"
      >
        <slot name="topbar" />
      </header>

      <main class="flex-1 px-6 py-6">
        <slot />
      </main>
    </div>
  </div>
</template>
```

```vue
<!-- ready — src/components/layout/SidebarNav.vue -->
<script setup lang="ts">
export interface NavGroup {
  label?: string                 // "PROJECT", "INTELLIGENCE", "ACTIONS", "SETTINGS"
  items: {
    label: string
    icon: string
    to: RouteLocationRaw
    permission?: string
    badge?: number | null
  }[]
}

defineProps<{ groups: NavGroup[] }>()
const auth = useAuthStore()
const ui = useUiStore()
</script>

<template>
  <nav class="flex-1 overflow-y-auto px-3 py-2">
    <div v-for="(group, gi) in groups" :key="gi" class="mb-5">
      <p
        v-if="group.label && !ui.sidebarCollapsed"
        class="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-mute"
      >
        {{ group.label }}
      </p>

      <template v-for="item in group.items" :key="item.label">
        <RouterLink
          v-if="!item.permission || auth.can(item.permission)"
          v-slot="{ isActive }"
          :to="item.to"
          custom
        >
          <a
            class="mb-0.5 flex h-10 items-center gap-3 rounded-[var(--pm-radius)] px-3 text-sm transition-colors"
            :class="isActive
              ? 'bg-[var(--pm-accent-dim)] font-medium text-accent'
              : 'text-dim hover:bg-surface-2 hover:text-fg'"
            @click="$router.push(item.to)"
          >
            <i :class="item.icon" class="size-[18px] shrink-0" />
            <span v-if="!ui.sidebarCollapsed" class="truncate">{{ item.label }}</span>
            <PmBadge v-if="item.badge && !ui.sidebarCollapsed" class="ml-auto" tone="danger">
              {{ item.badge }}
            </PmBadge>
          </a>
        </RouterLink>
      </template>
    </div>
  </nav>
</template>
```

**Project sidebar groups** — exactly as in `ui/project.png`:

```ts
// ready — src/components/layout/projectNav.ts
export function projectNavGroups(slug: string, counts: { failures?: number, pending?: number }): NavGroup[] {
  return [
    { label: 'Project', items: [
      { label: 'Overview',  icon: 'i-lucide-house',      to: { name: 'project.overview', params: { slug } } },
      { label: 'Pipelines', icon: 'i-lucide-git-branch', to: { name: 'project.pipelines', params: { slug } } },
      { label: 'Failures',  icon: 'i-lucide-triangle-alert', to: { name: 'project.failures', params: { slug } }, badge: counts.failures ?? null },
      { label: 'Analytics', icon: 'i-lucide-chart-column', to: { name: 'project.analytics', params: { slug } } },
    ] },
    { label: 'Intelligence', items: [
      { label: 'AI Analyses',     icon: 'i-lucide-sparkles',   to: { name: 'project.analyses', params: { slug } } },
      { label: 'Failure History', icon: 'i-lucide-history',    to: { name: 'project.history', params: { slug } } },
      { label: 'Knowledge',       icon: 'i-lucide-book-open',  to: { name: 'project.knowledge', params: { slug } } },
    ] },
    { label: 'Actions', items: [
      { label: 'Remediation', icon: 'i-lucide-wrench', to: { name: 'project.remediation', params: { slug } }, badge: counts.pending ?? null },
    ] },
    { label: 'Settings', items: [
      { label: 'Integration',      icon: 'i-lucide-plug',    to: { name: 'project.integration', params: { slug } }, permission: 'projects.manage' },
      { label: 'Project Settings', icon: 'i-lucide-settings', to: { name: 'project.settings', params: { slug } }, permission: 'projects.manage' },
    ] },
  ]
}
```

- [ ] `AppShell`, `SidebarNav`, `WorkspaceSidebar`, `ProjectSidebar`, `AppTopbar`, `UserMenu` built
- [ ] Collapse persists across reloads
- [ ] Mobile: sidebar becomes an overlay drawer under 1024px

---

## 12.6 Formatting utilities

Small, but they appear on every screen — get them right once.

```ts
// ready — src/utils/format.ts
export function duration(seconds: number | null | undefined): string {
  if (seconds == null)
    return '—'
  if (seconds < 60)
    return `${Math.round(seconds)}s`

  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)

  if (m < 60)
    return s ? `${m}m ${s}s` : `${m}m`

  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export function percent(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${v.toFixed(digits)}%`
}

export function compactNumber(n: number): string {
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(n)
}

export function bytes(n: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`
}

export function cost(usd: number): string {
  // Sub-cent costs are the norm; rounding to 2dp shows "$0.00" for every analysis
  // and makes the whole cost feature look broken.
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`
}

/** Delta color depends on which direction is good for THIS metric. */
export function deltaTone(delta: number | undefined, positiveDirection: 'up' | 'down' = 'up') {
  if (delta == null || delta === 0)
    return 'neutral'
  const good = positiveDirection === 'up' ? delta > 0 : delta < 0
  return good ? 'positive' : 'negative'
}
```

```ts
// ready — src/composables/useRelativeTime.ts
import { formatDistanceToNowStrict } from 'date-fns'

/** Live "2 min ago" that actually ticks. A static timestamp on a monitoring
 *  dashboard is worse than none — it looks fresh when it isn't. */
export function useRelativeTime(iso: MaybeRefOrGetter<string | null | undefined>) {
  const now = useNow({ interval: 30_000 })

  return computed(() => {
    const value = toValue(iso)
    if (!value)
      return '—'
    void now.value
    return `${formatDistanceToNowStrict(new Date(value))} ago`
  })
}
```

- [ ] Utilities written and unit-tested

---

## Definition of Done

- [ ] A `/_kitchen-sink` dev-only route renders every base component, chart and state
- [ ] Kitchen sink looks correct in dark **and** light
- [ ] No component hardcodes a hex outside `tokens.css` / metadata modules
- [ ] Lighthouse accessibility ≥ 95 on the kitchen sink
- [ ] Keyboard-only navigation reaches every interactive element with a visible focus ring

**Next:** [`13-frontend-public-auth.md`](13-frontend-public-auth.md)
