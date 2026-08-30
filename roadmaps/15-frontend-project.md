# 15 — Project Board

**Repo:** `PipeMind-front` · **Depends on:** 12, 14 · **Milestone:** M2

The project overview board. Target: [`../ui/project.png`](../ui/project.png) — build to match.

Data: **one request** — `GET /projects/{project}/overview?range=7d` (file 04) returns all eleven regions.

---

## 15.1 Layout

```text
┌──────────────┬───────────────────────────────────────────────────────────────────┐
│ ◆ PipeMind   │ Projects › biker-api › Overview   [🔍 Search ⌘K] [🔔3] [☀🌙] [👤] │
├──────────────┼───────────────────────────────────────────────────────────────────┤
│ ┌──────────┐ │ Overview                    [📅 Last 7 days ⌄] [⚙ Filters] [↻]    │
│ │BA biker- │ │                                                                   │
│ │   api  ⌄ │ │ Good evening, Oussema! 👋                                         │
│ │Laravel•… │ │ Here's what's happening with biker-api                            │
│ └──────────┘ │                                                                   │
│ PROJECT      │ ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐               │
│ 🏠 Overview ◄│ │↗ HEALTH││⚯ PIPE. ││! FAILS ││🕐 DUR. ││⏱ MTTR ││               │
│ ⚯ Pipelines  │ │ 98.2% ││  127  ││   3   ││3m 42s ││ 18m  ││                   │
│ ⚠ Failures   │ │↑3.6%  ││ ↑18   ││ ↓5    ││ ↓24s  ││ ↓7m  ││                   │
│ 📊 Analytics │ │∿∿∿∿∿  ││▁▃▅▂▇▄ ││▁▁▃▁▁  ││∿∿∿∿  ││∿∿∿∿  ││                    │
│              │ └────────┘└────────┘└────────┘└────────┘└────────┘               │
│ INTELLIGENCE │                                                                   │
│ ✦ AI Analyses│ ┌──────────────────────┐┌───────────────┐┌─────────────────────┐ │
│ 🕐 History   │ │ Pipeline Activity    ││Failure Break. ││ ✦ AI Insight    🧠  │ │
│ 📖 Knowledge │ │  ●Success ●Fail ●Run ││  View all     ││                     │ │
│              │ │  100 ┐               ││    ╭───╮      ││ Database readiness  │ │
│ ACTIONS      │ │   75 ┤∿∿∿∿∿∿∿       ││   │ 3  │      ││ issues in 2 pipe-   │ │
│ 🔧 Remediat. │ │   50 ┤               ││   │Total│     ││ lines last 24h.     │ │
│              │ │   25 ┤               ││    ╰───╯      ││ 32% above baseline. │ │
│ SETTINGS     │ │    0 ┴────────────   ││ ●DB 33%  1    ││                     │ │
│ 🔌 Integrat. │ │  May12 ...  May18    ││ ●Test 33% 1   ││   [Investigate]     │ │
│ ⚙ Project S. │ └──────────────────────┘└───────────────┘└─────────────────────┘ │
│              │                                                                   │
│              │ ┌─────────────────┐┌──────────────────────┐┌───────────────────┐ │
│              │ │Most Common      ││ Recent Pipelines     ││ Recent Activity   │ │
│              │ │Categories       ││ #821 Failed  2m14s   ││ ! #821 failed     │ │
│              │ │●DB   ███ 1 33%  ││ #820 Success 3m21s   ││ ✓ #820 completed  │ │
│ ┌──────────┐ │ │●Test ███ 1 33%  ││ #819 Running 24m12s  ││ ⚠ long running    │ │
│ │OU Oussema│ │ │●Dep  ███ 1 33%  ││ #818 Success 3m02s   ││ ✦ AI analysis     │ │
│ │  Admin  ⌄│ │ │●Dock ░░░ 0 0%   ││ #817 Failed  1m48s   ││ [View all]        │ │
│ └──────────┘ │ └─────────────────┘└──────────────────────┘└───────────────────┘ │
│ « Collapse   │ ┌───────────────────────────────────────────────────────────────┐ │
│              │ │ Pipeline Success Rate ⓘ                      [Last 30 days ⌄] │ │
│              │ │ 98.2%   100%│▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐▐                  │ │
│              │ │ +3.6%    50%│                                                 │ │
│              │ │           0%└──Apr20────Apr27────May04────May11────May18──── │ │
└──────────────┴───────────────────────────────────────────────────────────────────┘
```

```vue
<!-- ready — src/views/project/ProjectOverviewView.vue -->
<script setup lang="ts">
const props = defineProps<{ slug: string }>()

const range = useRouteQuery<RangeKey>('range', '7d')
const { data, isLoading, error, refetch, isFetching } = useProjectOverview(props.slug, range)

// Live-refresh only while something is actually running.
const hasRunning = computed(() =>
  data.value?.recent_pipelines.some(p => p.status === 'running' || p.status === 'queued') ?? false)
</script>

<template>
  <div class="mx-auto max-w-[1700px]">
    <ProjectPageHeader
      title="Overview"
      v-model:range="range"
      :refreshing="isFetching"
      @refresh="refetch"
    />

    <ProjectGreeting :project="data?.project" class="mt-5" />

    <PmAsyncBoundary :loading="isLoading" :error="error" @retry="refetch">
      <ProjectKpiRow :kpis="data!.kpis" class="mt-6" />

      <!-- row 1 -->
      <div class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1.1fr)]">
        <PipelineActivityChart :chart="data!.activity_chart" />
        <FailureBreakdownCard :breakdown="data!.failure_breakdown" :slug="slug" />
        <AiInsightCard :insight="data!.insight" :slug="slug" />
      </div>

      <!-- row 2 -->
      <div class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_minmax(0,1.1fr)]">
        <TopCategoriesCard :categories="data!.top_categories" :slug="slug" />
        <RecentPipelinesCard :pipelines="data!.recent_pipelines" :slug="slug" />
        <ActivityPanel :items="data!.recent_activity" title="Recent Activity"
                       :to="{ name: 'project.pipelines', params: { slug } }" />
      </div>

      <!-- row 3 -->
      <SuccessRateCard :chart="data!.success_rate_chart" class="mt-5" />
    </PmAsyncBoundary>
  </div>
</template>
```

```ts
// ready — src/api/queries/project.ts
export function useProjectOverview(slug: MaybeRef<string>, range: MaybeRef<RangeKey>) {
  const hasRunning = ref(false)

  return useQuery({
    queryKey: ['project', slug, 'overview', range],
    queryFn: async () => {
      const res = await api.get(`/projects/${unref(slug)}/overview`, { params: { range: unref(range) } })
      const data = res.data.data as ProjectOverview
      hasRunning.value = data.recent_pipelines.some(p => ['running', 'queued'].includes(p.status))
      return data
    },
    staleTime: 20_000,
    // Poll fast while a pipeline is in flight, slowly otherwise, never when hidden.
    refetchInterval: () => (hasRunning.value ? 8_000 : 60_000),
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,     // no flash when the range changes
  })
}
```

> **`keepPreviousData` on range change** is the difference between a board that feels instant and one that blanks out every time you touch the date picker. The old data stays visible, dimmed via `isFetching`, until the new payload lands.

---

## 15.2 Page header

```vue
<!-- ready — src/components/project/ProjectPageHeader.vue -->
<script setup lang="ts">
const RANGES = [
  { key: '24h', label: 'Last 24 hours' },
  { key: '7d',  label: 'Last 7 days' },
  { key: '30d', label: 'Last 30 days' },
  { key: '90d', label: 'Last 90 days' },
] as const

const range = defineModel<RangeKey>('range', { required: true })
defineProps<{ title: string, refreshing?: boolean }>()
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <h1 class="text-2xl font-semibold">{{ title }}</h1>

    <div class="flex items-center gap-2">
      <PmSelect v-model="range" :options="RANGES" icon="i-lucide-calendar" class="w-[168px]" />

      <PmButton variant="secondary" size="md">
        <i-lucide-sliders-horizontal class="size-4" /> Filters
      </PmButton>

      <PmButton variant="secondary" size="md" aria-label="Refresh" @click="$emit('refresh')">
        <i-lucide-refresh-cw class="size-4" :class="refreshing && 'animate-spin'" />
      </PmButton>
    </div>
  </div>
</template>
```

---

## 15.3 KPI row — five tiles with sparklines

Same `KpiTile` as file 14, extended with a sparkline slot. Note the differing sparkline types in the mockup: line for health, **bars** for pipelines and failures, line for duration and MTTR.

```vue
<!-- ready — src/components/project/ProjectKpiRow.vue -->
<script setup lang="ts">
defineProps<{ kpis: ProjectOverview['kpis'] }>()

const TILES = [
  { key: 'pipeline_health', label: 'Pipeline Health', icon: 'i-lucide-trending-up',  color: 'var(--pm-accent)',  spark: 'line' },
  { key: 'pipelines',       label: 'Pipelines',       icon: 'i-lucide-git-branch',   color: 'var(--pm-accent)',  spark: 'bar'  },
  { key: 'failures',        label: 'Failures',        icon: 'i-lucide-circle-alert', color: 'var(--pm-danger)',  spark: 'bar'  },
  { key: 'avg_duration',    label: 'Avg. Duration',   icon: 'i-lucide-clock',        color: 'var(--pm-running)', spark: 'line' },
  { key: 'mttr',            label: 'MTTR',            icon: 'i-lucide-timer',        color: 'var(--pm-ai)',      spark: 'line' },
] as const
</script>

<template>
  <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
    <PmCard v-for="t in TILES" :key="t.key" hoverable>
      <div class="flex items-start gap-3">
        <PmIconTile :icon="t.icon" :color="t.color" size="sm" />
        <div class="min-w-0 flex-1">
          <p class="text-[13px] font-medium text-dim">{{ t.label }}</p>
          <p class="mt-1 text-[26px] font-semibold leading-none tnum">
            {{ kpis[t.key].display ?? `${kpis[t.key].value}${kpis[t.key].unit ?? ''}` }}
          </p>
          <DeltaLabel :metric="kpis[t.key]" class="mt-1.5" />
        </div>
      </div>

      <PmSparkline
        class="mt-3"
        :data="kpis[t.key].spark ?? []"
        :type="t.spark"
        :color="t.color"
        :height="38"
      />
    </PmCard>
  </div>
</template>
```

```vue
<!-- ready — src/components/project/DeltaLabel.vue -->
<script setup lang="ts">
const props = defineProps<{ metric: Metric }>()

const tone = computed(() => deltaTone(props.metric.delta, props.metric.positive_direction ?? 'up'))
const arrow = computed(() => (props.metric.delta ?? 0) >= 0 ? 'i-lucide-arrow-up' : 'i-lucide-arrow-down')
</script>

<template>
  <p
    class="flex items-center gap-1 text-[11px] font-medium"
    :class="{ positive: 'text-accent', negative: 'text-[var(--pm-danger)]', neutral: 'text-dim' }[tone]"
  >
    <i :class="arrow" class="size-3" />
    {{ metric.delta_label }}
  </p>
</template>
```

> **The arrow direction and the color are independent.** MTTR falling shows a *down* arrow in *green*, because `positive_direction: "down"` came from the server. Deriving color from the arrow is the bug that makes every improvement look like a regression.

---

## 15.4 Pipeline Activity chart

```vue
<!-- ready — src/components/project/PipelineActivityChart.vue -->
<script setup lang="ts">
import { Line } from 'vue-chartjs'
import { AXIS } from '@/components/charts/chartDefaults'

const props = defineProps<{ chart: ActivityChart }>()
const granularity = ref<'hourly' | 'daily' | 'weekly'>('daily')

const chartData = computed(() => ({
  labels: props.chart.series[0]?.points.map(p => format(new Date(p.x), 'MMM d')) ?? [],
  datasets: props.chart.series.map(s => ({
    label: s.label,
    data: s.points.map(p => p.y),
    borderColor: s.color,
    backgroundColor: `color-mix(in srgb, ${s.color} 14%, transparent)`,
    borderWidth: 2,
    tension: 0.35,
    pointRadius: 2.5,
    pointHoverRadius: 5,
    pointBackgroundColor: s.color,
    pointBorderColor: 'var(--pm-bg)',
    pointBorderWidth: 2,
    fill: s.key === 'success',        // only the success band is filled, per the mockup
  })),
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  // One tooltip listing all three series at the hovered x — comparing across
  // separate tooltips is exactly the work the chart should be doing for you.
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: { callbacks: { title: (i: any[]) => i[0]?.label ?? '' } },
  },
  scales: {
    x: { ...AXIS, grid: { display: false } },
    y: { ...AXIS, beginAtZero: true, ticks: { ...AXIS.ticks, stepSize: 25 } },
  },
}
</script>

<template>
  <PmCard title="Pipeline Activity" :padded="false">
    <template #actions>
      <div class="flex items-center gap-4">
        <ChartLegend :series="chart.series" />
        <PmSelect v-model="granularity" :options="GRANULARITIES" size="sm" class="w-[104px]" />
      </div>
    </template>

    <div class="h-[240px] px-4 pb-4">
      <Line :data="chartData" :options="options" />
    </div>
  </PmCard>
</template>
```

```vue
<!-- ready — src/components/charts/ChartLegend.vue -->
<!-- Rendered in Vue, not on canvas: clickable to toggle series, theme-aware, accessible. -->
<template>
  <ul class="flex items-center gap-3">
    <li v-for="s in series" :key="s.key">
      <button
        class="flex items-center gap-1.5 text-[11px] transition-opacity"
        :class="hidden.has(s.key) ? 'opacity-40' : 'text-dim'"
        @click="toggle(s.key)"
      >
        <span class="size-2 rounded-full" :style="{ background: s.color }" />
        {{ s.label }}
      </button>
    </li>
  </ul>
</template>
```

---

## 15.5 Failure Breakdown donut

```vue
<!-- ready — src/components/project/FailureBreakdownCard.vue -->
<script setup lang="ts">
import { Doughnut } from 'vue-chartjs'

const props = defineProps<{ breakdown: FailureBreakdown, slug: string }>()

const chartData = computed(() => ({
  labels: props.breakdown.items.map(i => i.label),
  datasets: [{
    data: props.breakdown.items.map(i => i.count),
    backgroundColor: props.breakdown.items.map(i => i.color),
    borderWidth: 0,
    // Slight expansion on hover instead of a border — a border on a 0-count
    // slice draws a visible ring where there is no data.
    hoverOffset: 6,
  }],
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '68%',
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (c: any) => {
          const item = props.breakdown.items[c.dataIndex]
          return ` ${item.label}: ${item.count} (${item.percentage.toFixed(0)}%)`
        },
      },
    },
  },
}
</script>

<template>
  <PmCard title="Failure Breakdown" :padded="false">
    <template #actions>
      <RouterLink
        :to="{ name: 'project.failures', params: { slug } }"
        class="text-xs font-medium text-accent hover:underline"
      >View all</RouterLink>
    </template>

    <div class="flex items-center gap-5 px-4 pb-4">
      <div class="relative size-[132px] shrink-0">
        <Doughnut :data="chartData" :options="options" />
        <div class="pointer-events-none absolute inset-0 grid place-items-center">
          <p class="text-[26px] font-semibold leading-none tnum">{{ breakdown.total }}</p>
          <p class="text-[11px] text-dim">Total</p>
        </div>
      </div>

      <ul class="min-w-0 flex-1 space-y-2.5">
        <li v-for="item in breakdown.items" :key="item.category">
          <RouterLink
            :to="{ name: 'project.failures', params: { slug }, query: { category: item.category } }"
            class="flex items-center gap-2 text-[13px] transition-colors hover:text-fg"
            :class="item.count === 0 ? 'text-mute' : 'text-dim'"
          >
            <span class="size-2 shrink-0 rounded-full" :style="{ background: item.color }" />
            <span class="min-w-0 flex-1 truncate">{{ item.label }}</span>
            <span class="tnum">{{ item.percentage.toFixed(0) }}%</span>
            <span class="w-4 text-right font-medium tnum text-fg">{{ item.count }}</span>
          </RouterLink>
        </li>
      </ul>
    </div>
  </PmCard>
</template>
```

**Legend rows are filter links.** Clicking "Database 33% 1" navigates to the failures list pre-filtered to `DATABASE`. That single decision turns a decorative chart into the entry point for the investigation workflow.

---

## 15.6 AI Insight card

The visual centrepiece: lime glow border, sparkle icon, brain graphic, `Investigate` CTA.

```vue
<!-- ready — src/components/project/AiInsightCard.vue -->
<script setup lang="ts">
const props = defineProps<{ insight: ProjectInsight | null, slug: string }>()
const router = useRouter()

function investigate() {
  if (!props.insight?.action) return
  router.push({
    name: `project.${props.insight.action.route}`,
    params: { slug: props.slug },
    query: props.insight.action.params,
  })
}
</script>

<template>
  <PmCard v-if="insight" glow :padded="false" class="overflow-hidden">
    <div class="relative p-5">
      <!-- decorative neural graphic, bleeding off the right edge like the mockup -->
      <NeuralGraphic
        class="pointer-events-none absolute -right-6 top-1/2 size-[150px] -translate-y-1/2 opacity-70"
        aria-hidden="true"
      />

      <div class="relative max-w-[62%]">
        <div class="flex items-center gap-2">
          <i-lucide-sparkles class="size-4 text-accent" />
          <h3 class="text-[15px] font-semibold">AI Insight</h3>
        </div>

        <p class="mt-3 text-[13px] leading-relaxed text-dim">
          <!-- The headline carries emphasis on the specific numbers — that's the
               information the reader is actually scanning for. -->
          <span v-html="highlightNumbers(insight.headline)" />
        </p>
        <p v-if="insight.detail" class="mt-1.5 text-[13px] leading-relaxed text-dim">
          {{ insight.detail }}
        </p>

        <PmButton variant="primary" size="sm" class="mt-4" @click="investigate">
          {{ insight.action?.label ?? 'Investigate' }}
        </PmButton>
      </div>
    </div>
  </PmCard>

  <!-- No insight is a legitimate, positive state — say so rather than hiding the card
       and leaving a hole in the grid. -->
  <PmCard v-else class="grid place-items-center text-center">
    <div class="py-6">
      <i-lucide-sparkles class="mx-auto size-6 text-mute" />
      <p class="mt-3 text-[13px] font-medium">No patterns detected</p>
      <p class="mt-1 text-xs text-dim">PipeMind hasn't found anything unusual in this range.</p>
    </div>
  </PmCard>
</template>
```

**Where the insight comes from** (backend, `ProjectInsightService`) — deterministic rules over the metrics, not an extra LLM call:

| Rule | Insight |
|---|---|
| One category ≥ 40% of failures in range | "Database issues account for 45% of failures this week." |
| Category count > 1.3× the 30-day baseline | "Database readiness issues detected in 2 pipelines in the last 24h. 32% higher than your normal baseline." |
| Open duration anomaly | "Build duration is 4.1× your project average." |
| Same signature ≥ 3× in 7 days | "The same dependency conflict has failed 4 pipelines this week." |
| Success rate down > 10 points | "Success rate dropped from 98% to 84% after Tuesday." |
| Flaky test detected | "3 tests failed and passed on the same commit — likely flaky." |
| Nothing matches | `null` → the empty state above |

> **Generating this card with an LLM would be wasteful and unreliable.** These are aggregate facts already in `project_metrics_daily`. Rules give you an instant, free, always-correct insight; save the model for the failures where reasoning is actually required.

- [ ] `ProjectInsightService` implemented with the 6 rules
- [ ] `AiInsightCard` + `NeuralGraphic` (inline SVG) built

---

## 15.7 Top categories & recent pipelines

```vue
<!-- ready — src/components/project/TopCategoriesCard.vue -->
<template>
  <PmCard title="Most Common Failure Categories" :padded="false">
    <template #actions>
      <RouterLink :to="{ name: 'project.failures', params: { slug } }"
                  class="text-xs font-medium text-accent hover:underline">View all</RouterLink>
    </template>

    <ul class="space-y-3 px-4 pb-4">
      <li v-for="c in categories" :key="c.category" class="flex items-center gap-3">
        <PmIconTile :icon="CATEGORY_META[c.category].icon" :color="c.color" size="sm" />
        <span class="w-[92px] shrink-0 truncate text-[13px]"
              :class="c.count === 0 ? 'text-mute' : 'text-fg'">{{ c.label }}</span>

        <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-3">
          <div
            class="h-full rounded-full transition-[width] duration-500"
            :style="{ width: `${c.percentage}%`, background: c.color }"
          />
        </div>

        <span class="w-[58px] shrink-0 text-right text-xs tabular-nums text-dim">
          {{ c.count }} ({{ c.percentage.toFixed(0) }}%)
        </span>
      </li>
    </ul>
  </PmCard>
</template>
```

```vue
<!-- ready — src/components/project/RecentPipelinesCard.vue -->
<template>
  <PmCard title="Recent Pipelines" :padded="false">
    <template #actions>
      <RouterLink :to="{ name: 'project.pipelines', params: { slug } }"
                  class="text-xs font-medium text-accent hover:underline">View all</RouterLink>
    </template>

    <table class="w-full text-[13px]">
      <thead>
        <tr class="border-b text-[10px] uppercase tracking-wider text-mute">
          <th class="px-4 py-2 text-left font-medium">Pipeline</th>
          <th class="px-2 py-2 text-left font-medium">Status</th>
          <th class="px-2 py-2 text-left font-medium">Branch</th>
          <th class="px-2 py-2 text-right font-medium">Duration</th>
          <th class="px-4 py-2 text-right font-medium">Finished</th>
        </tr>
      </thead>

      <tbody class="divide-y">
        <tr
          v-for="p in pipelines" :key="p.uuid"
          class="cursor-pointer transition-colors hover:bg-surface-2"
          @click="open(p)"
        >
          <td class="px-4 py-2.5">
            <span class="flex items-center gap-1.5 font-medium">
              <ProviderIcon :provider="p.provider" class="size-3.5" />
              #{{ p.iid }}
            </span>
          </td>
          <td class="px-2 py-2.5"><PmStatusPill :status="p.status" size="sm" /></td>
          <td class="max-w-[140px] truncate px-2 py-2.5 text-dim">{{ p.ref }}</td>
          <td class="px-2 py-2.5 text-right tabular-nums text-dim">
            {{ p.duration_display ?? duration(p.duration_seconds) }}
          </td>
          <td class="px-4 py-2.5 text-right text-mute">{{ relative(p.finished_at) }}</td>
        </tr>
      </tbody>
    </table>

    <PmEmptyState v-if="!pipelines.length" compact title="No pipelines in this range" />
  </PmCard>
</template>
```

> **A failed row routes to the *failure*, not the pipeline.** When `has_failure` is true, the user's next question is "why", and the failure page answers it directly. Sending them to the pipeline page to click one more time is a wasted step in the most common path in the product.

---

## 15.8 Success rate chart

```vue
<!-- ready — src/components/project/SuccessRateCard.vue -->
<script setup lang="ts">
import { Bar } from 'vue-chartjs'

const props = defineProps<{ chart: SuccessRateChart }>()
const range = ref<'30d' | '90d'>('30d')

const chartData = computed(() => ({
  labels: props.chart.bars.map(b => format(new Date(b.date), 'MMM dd')),
  datasets: [{
    data: props.chart.bars.map(b => b.success_rate),
    // Per-bar color by threshold: a bad day is visible without reading the axis.
    backgroundColor: props.chart.bars.map(b =>
      b.success_rate >= 95 ? 'var(--pm-accent)'
      : b.success_rate >= 80 ? 'var(--pm-warning)'
        : 'var(--pm-danger)'),
    borderRadius: 2,
    barPercentage: 0.72,
    categoryPercentage: 0.85,
  }],
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (c: any) => {
          const b = props.chart.bars[c.dataIndex]
          return [` ${b.success_rate.toFixed(1)}% success`,
                  ` ${b.total} pipelines, ${b.failed} failed`]
        },
      },
    },
  },
  scales: {
    x: { ...AXIS, grid: { display: false }, ticks: { ...AXIS.ticks, maxTicksLimit: 6 } },
    y: { ...AXIS, min: 0, max: 100, ticks: { ...AXIS.ticks, stepSize: 50, callback: (v: number) => `${v}%` } },
  },
}
</script>

<template>
  <PmCard :padded="false">
    <template #header>
      <div class="flex w-full items-center justify-between px-5 pb-3 pt-4">
        <h3 class="flex items-center gap-1.5 text-[15px] font-semibold">
          Pipeline Success Rate
          <PmTooltip content="Percentage of pipelines that completed successfully each day.">
            <i-lucide-info class="size-3.5 text-mute" />
          </PmTooltip>
        </h3>
        <PmSelect v-model="range" :options="[{ key: '30d', label: 'Last 30 days' }, { key: '90d', label: 'Last 90 days' }]" size="sm" class="w-[150px]" />
      </div>
    </template>

    <div class="grid gap-6 px-5 pb-5 lg:grid-cols-[168px_minmax(0,1fr)]">
      <div class="self-center">
        <p class="text-[34px] font-semibold leading-none tnum">{{ chart.value.toFixed(1) }}%</p>
        <p class="mt-2 text-xs font-medium text-accent">+ {{ chart.delta.toFixed(1) }}% vs last 7 days</p>
      </div>

      <div class="h-[150px]"><Bar :data="chartData" :options="options" /></div>
    </div>
  </PmCard>
</template>
```

---

## 15.9 Project sidebar & switcher

```vue
<!-- ready — src/components/layout/ProjectSwitcher.vue -->
<template>
  <PmDropdown align="start" :width="300">
    <template #trigger>
      <button class="mx-3 mt-3 flex w-[calc(100%-24px)] items-center gap-3 rounded-[var(--pm-radius)]
                     border bg-surface p-3 text-left transition-colors hover:bg-surface-2">
        <span
          class="grid size-9 shrink-0 place-items-center rounded-[var(--pm-radius-sm)] text-xs font-semibold"
          :style="{ background: `color-mix(in srgb, ${project.color} 18%, transparent)`, color: project.color }"
        >{{ project.initials }}</span>

        <span class="min-w-0 flex-1">
          <span class="block truncate text-[13px] font-semibold">{{ project.name }}</span>
          <span class="block truncate text-[11px] text-dim">{{ project.tech_stack.join(' · ') }}</span>
        </span>

        <i-lucide-chevron-down class="size-4 shrink-0 text-mute" />
      </button>
    </template>

    <!-- searchable list of the team's projects + "View all projects" -->
    <ProjectSwitcherList />
  </PmDropdown>
</template>
```

The sidebar uses `projectNavGroups()` from file 12, with badge counts fed by `useProjectCounts(slug)` (open failures, pending remediations). Bottom: user card + `« Collapse`.

**Topbar** (project shell): breadcrumb `Projects › biker-api › Overview`, global ⌘K search, bell, theme toggle, avatar.

```ts
// ready — src/composables/useCommandPalette.ts
// ⌘K / Ctrl+K opens the palette. Searches projects, pipelines (#821), failures,
// and error signatures via GET /search. Also exposes actions: "Retry #821",
// "Go to failures", "Switch project".
onKeyStroke(['k', 'K'], (e) => {
  if (e.metaKey || e.ctrlKey) {
    e.preventDefault()
    ui.commandPaletteOpen = true
  }
})
```

- [ ] `ProjectShell`, `ProjectSwitcher`, breadcrumb, command palette built

---

## Definition of Done

- [ ] The board is **visually indistinguishable from `ui/project.png`** at 1536×1024
- [ ] One network request populates all eleven regions
- [ ] Changing the range keeps the old data visible while refetching
- [ ] Polling is 8 s while a pipeline runs, 60 s otherwise, paused when the tab is hidden
- [ ] Donut legend rows filter the failures list
- [ ] Failed pipeline rows route to the failure, not the pipeline
- [ ] `AiInsightCard` renders all six rule types and the empty state
- [ ] MTTR improving shows a green down-arrow
- [ ] Responsive: 5→3→2→1 KPI columns; three-column rows stack at < 1280px
- [ ] Light theme correct, including chart colors
- [ ] ⌘K opens the palette and finds a pipeline by `#iid`

**Next:** [`16-frontend-failure-investigation.md`](16-frontend-failure-investigation.md)
