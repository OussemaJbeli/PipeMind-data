# 16 — Failure Investigation

**Repo:** `PipeMind-front` · **Depends on:** 15 · **Milestone:** M3 ⭐

Pipelines list, pipeline detail, the log viewer, and the **failure detail page** — where the whole product justifies itself. This is the screen that turns "your pipeline failed" into "here is why, here is the proof, here is the fix".

---

## 16.1 Pipelines list — `/app/projects/:slug/pipelines`

```text
Pipelines                              [Status ⌄][Branch ⌄][Source ⌄][📅 7d ⌄]
┌────────────────────────────────────────────────────────────────────────────┐
│ PIPELINE  STATUS   BRANCH          COMMIT   TRIGGERED BY  DURATION  FINISHED│
├────────────────────────────────────────────────────────────────────────────┤
│ 🦊 #821   ✗Failed  feature/payment a82c91  Oussema        2m 14s   2 min ago│
│           └─ ⚠ DATABASE · Connection refused        [View analysis →]       │
│ 🦊 #820   ✓Success main            3f91ad  Oussema        3m 21s  15 min ago│
│ 🦊 #819   ◐Running feature/auth    91bd2c  Sarah         24m 12s      —     │
│           └─ ⚠ Running 4.1× longer than usual                              │
└────────────────────────────────────────────────────────────────────────────┘
```

**Expanded sub-rows carry the value.** A plain list of pipelines is what GitLab already gives you. The failure summary and the anomaly warning inline are what makes this list worth visiting instead.

```vue
<!-- ready — src/views/project/PipelinesView.vue (key parts) -->
<script setup lang="ts">
const filters = reactive({
  status: useRouteQuery('status', ''),
  ref: useRouteQuery('ref', ''),
  source: useRouteQuery('source', ''),
  range: useRouteQuery<RangeKey>('range', '7d'),
})

const page = useRouteQuery('page', 1, { transform: Number })
const { data, isLoading, error } = usePipelines(props.slug, filters, page)

// Poll only while something is in flight; stop entirely when nothing is running.
const anyRunning = computed(() =>
  data.value?.data.some(p => ['running', 'queued'].includes(p.status)) ?? false)
</script>
```

- [ ] Filters live in the URL — a filtered view must be shareable and survive reload
- [ ] Server-side pagination (25/page), keyboard-navigable rows
- [ ] Running rows animate their duration upward live

---

## 16.2 Pipeline detail — `/app/projects/:slug/pipelines/:iid`

```text
Projects › biker-api › Pipelines › #821

┌────────────────────────────────────────────────────────────────────────┐
│ ✗ Pipeline #821  ·  feature/payment  ·  a82c91                         │
│ "wire payment webhook"  ·  Oussema  ·  2m 14s  ·  2 min ago            │
│                              [Open in GitLab ↗] [Retry pipeline]       │
└────────────────────────────────────────────────────────────────────────┘

  checkout      install       lint          test          build    deploy
  ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌───────┐ ┌──────┐
  │✓ 4s    │──▶│✓ 38s   │──▶│✓ 12s   │──▶│✗ 94s   │──▶│○      │▶│○     │
  │checkout│   │npm ci  │   │eslint  │   │backend │   │build  │ │deploy│
  └────────┘   └────────┘   └────────┘   │-tests  │   └───────┘ └──────┘
                                          └────────┘
                                             ▲ failed

┌─ Failure detected ─────────────────────────────────────────────────────┐
│ ⚠ DATABASE / ConnectionRefused · HIGH                                  │
│ SQLSTATE[HY000] [2002] Connection refused                              │
│ ✦ Analysed · 92% confidence          [View full analysis →]            │
└────────────────────────────────────────────────────────────────────────┘

[ Jobs ]  [ Changes (2) ]  [ Logs ]
```

```vue
<!-- ready — src/components/project/PipelineGraph.vue -->
<script setup lang="ts">
// Horizontal stage flow with jobs stacked inside each stage.
// Deliberately NOT a generic DAG renderer: GitLab/GitHub/Jenkins all model
// pipelines as ordered stages containing parallel jobs, and that is exactly
// what the normalized model in file 02 stores. Building a full dependency
// graph would render relationships we never ingest.
defineProps<{ stages: PipelineStage[], jobs: PipelineJob[] }>()
</script>

<template>
  <div class="flex items-start gap-2 overflow-x-auto pb-2">
    <template v-for="(stage, i) in stages" :key="stage.name">
      <div class="min-w-[148px] shrink-0">
        <p class="mb-2 text-[11px] font-medium uppercase tracking-wide text-mute">{{ stage.name }}</p>
        <div class="space-y-2">
          <JobNode
            v-for="job in jobsFor(stage)" :key="job.uuid"
            :job="job" @click="$emit('select', job)"
          />
        </div>
      </div>

      <i-lucide-chevron-right
        v-if="i < stages.length - 1"
        class="mt-8 size-4 shrink-0 text-mute"
      />
    </template>
  </div>
</template>
```

- [ ] `PipelineGraph`, `JobNode`, `PipelineHeader`, `ChangedFilesTab` built
- [ ] Retry buttons respect permissions and show the policy decision

---

## 16.3 Log viewer

The component that has to handle a 48,000-line file without freezing the browser.

```vue
<!-- ready — src/components/failure/LogViewer.vue -->
<script setup lang="ts">
import { useVirtualList } from '@vueuse/core'

const props = defineProps<{
  jobUuid: string
  highlightLines?: number[]
  autoScrollToError?: boolean
}>()

const mode = ref<'excerpt' | 'full'>('excerpt')
const { data, isLoading } = useJobLog(props.jobUuid, mode)

// Virtualise the full log. Rendering 48k DOM nodes locks the main thread for
// seconds; the excerpt is small enough to render directly.
const { list, containerProps, wrapperProps, scrollTo } = useVirtualList(
  computed(() => data.value?.lines ?? []),
  { itemHeight: 20, overscan: 30 },
)

const highlighted = computed(() => new Set(props.highlightLines ?? []))

watch(data, (d) => {
  if (!d || !props.autoScrollToError) return
  const first = d.lines.findIndex(l => l.highlight)
  if (first >= 0) nextTick(() => scrollTo(Math.max(0, first - 6)))
}, { immediate: true })
</script>

<template>
  <PmCard :padded="false">
    <template #header>
      <div class="flex w-full items-center justify-between gap-3 px-4 pb-2.5 pt-3">
        <div class="flex items-center gap-2 text-xs text-dim">
          <i-lucide-terminal class="size-3.5" />
          <span class="tnum">{{ data?.line_count.toLocaleString() }} lines</span>
          <span class="text-mute">·</span>
          <span>{{ bytes(data?.size_bytes ?? 0) }}</span>

          <!-- Redaction is a feature. Say it happened, and say what was removed. -->
          <PmTooltip v-if="data?.is_redacted" :content="`Removed: ${data.redaction_types.join(', ')}`">
            <PmBadge tone="accent" class="ml-1">
              <i-lucide-shield-check class="size-3" />
              {{ data.redaction_count }} redacted
            </PmBadge>
          </PmTooltip>
        </div>

        <div class="flex items-center gap-2">
          <PmSegmented
            v-model="mode"
            :options="[{ key: 'excerpt', label: 'Relevant' }, { key: 'full', label: 'Full log' }]"
            size="sm"
          />
          <PmButton size="sm" variant="ghost" @click="copy">
            <i-lucide-copy class="size-3.5" />
          </PmButton>
          <PmButton size="sm" variant="ghost" @click="download">
            <i-lucide-download class="size-3.5" />
          </PmButton>
        </div>
      </div>
    </template>

    <p v-if="mode === 'excerpt' && data" class="border-y bg-surface-2 px-4 py-1.5 text-[11px] text-dim">
      Showing lines {{ data.excerpt_start_line }}–{{ data.excerpt_end_line }} — the region
      PipeMind identified as relevant.
      <button class="text-accent hover:underline" @click="mode = 'full'">Show full log</button>
    </p>

    <div v-bind="containerProps" class="max-h-[520px] overflow-auto bg-[#08090B] font-mono text-[12px] leading-5">
      <div v-bind="wrapperProps">
        <div
          v-for="{ data: line, index } in list" :key="index"
          class="group flex"
          :class="line.highlight && 'bg-[color:var(--pm-danger)]/8'"
        >
          <span
            class="w-14 shrink-0 select-none border-r px-2 text-right text-mute"
            :class="line.highlight && 'border-[var(--pm-danger)] text-[var(--pm-danger)]'"
          >{{ line.n }}</span>

          <code
            class="whitespace-pre-wrap break-all px-3"
            :class="{
              'text-[var(--pm-danger)]': line.level === 'error',
              'text-[var(--pm-warning)]': line.level === 'warn',
              'text-[#C9D1D9]': !line.level || line.level === 'info',
            }"
          >{{ line.text }}</code>
        </div>
      </div>
    </div>
  </PmCard>
</template>
```

**Log viewer requirements:**

| Requirement | Reason |
|---|---|
| Virtualised list | 48k lines will freeze the tab otherwise |
| "Relevant" is the **default** tab | The extract is the product; the full log is the escape hatch |
| Error lines highlighted + auto-scrolled | The user should land on the problem, not line 1 |
| Redaction badge with types | Users must know something was removed and what kind |
| Line numbers are the real numbers | `source_ref: "job_logs#L1294"` from the analysis must resolve here |
| Download via signed URL | Never stream 50 MB through the API |
| No `v-html`, ever | Log content is untrusted input from third-party systems |

> **Never render log content with `v-html`.** CI logs contain arbitrary attacker-influenceable text — a dependency name, a commit message, a test fixture. Interpolation escapes it; `v-html` executes it.

- [ ] `LogViewer` built with virtualisation
- [ ] Deep link `#L1294` scrolls to and flashes that line

---

## 16.4 Failure detail — the flagship screen

```text
Projects › biker-api › Failures › DATABASE / Connection refused

┌──────────────────────────────────────────────────────────────────────────┐
│ ⚠ HIGH   DATABASE / ConnectionRefused           4th occurrence           │
│ SQLSTATE[HY000] [2002] Connection refused                                │
│ Pipeline #821 · test · backend-tests · feature/payment · 2 min ago       │
│                    [Mark resolved] [Ignore] [Re-analyse] [Open in GitLab]│
└──────────────────────────────────────────────────────────────────────────┘

┌─ OBSERVED ───────────────────────────────────────┐ ┌─ SIMILAR FAILURES ──┐
│ Facts collected from your pipeline.              │ │ 94%  #921  3mo ago  │
│                                                  │ │ Database container  │
│ Changed in this commit                           │ │ not ready           │
│ ⚙ docker-compose.yml        +4 −1  [CONFIG]      │ │ ✓ Fixed: healthcheck│
│ 📄 app/Services/Payment.php +62 −8               │ │ ─────────────────── │
│                                                  │ │ 87%  #874  5mo ago  │
│ Previous pipeline #820 on feature/payment ✓      │ │ ...                 │
│                                                  │ └─────────────────────┘
│ Log excerpt  lines 1281–1310                     │
│ ┌──────────────────────────────────────────────┐ │ ┌─ RECOMMENDED ───────┐
│ │1294│ SQLSTATE[HY000] [2002] Connection refu…│ │ │ 1. Add a database   │
│ └──────────────────────────────────────────────┘ │ │    readiness check  │
└──────────────────────────────────────────────────┘ │    Risk: LOW        │
                                                     │    [Review] [Apply] │
┌─ PIPEMIND ANALYSIS ─────────────── 92% ──────────┐ │ ─────────────────── │
│ ✦ Database was unavailable when integration      │ │ 2. Increase startup │
│   tests started.                                 │ │    timeout          │
│                                                  │ │    Risk: LOW        │
│ The database container had not finished its      │ └─────────────────────┘
│ startup sequence before the test job began       │
│ connecting. docker-compose.yml was modified in   │
│ this commit and the healthcheck-based depends_on │
│ condition was removed.                           │
│                                                  │
│ EVIDENCE                                         │
│ ▪ Connection refused on port 5432    log L1294   │
│ ▪ docker-compose.yml — depends_on removed  ⚙     │
│ ▪ Failure #921 had the same signature      94%   │
│                                                  │
│ hybrid · RAG · gemini-2.0-flash · 3.8s · $0.0004 │
│ Was this helpful?  [👍] [👎]                     │
└──────────────────────────────────────────────────┘
```

```vue
<!-- ready — src/views/project/FailureDetailView.vue -->
<template>
  <div class="mx-auto max-w-[1500px]">
    <FailureHeader :failure="failure" @resolve="…" @ignore="…" @reanalyse="…" />

    <div class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div class="space-y-5">
        <!-- FACTS -->
        <ObservedPanel :observed="failure.observed" :job="failure.job" />

        <!-- INFERENCE -->
        <AnalysisPanel
          :analysis="failure.analysis"
          :status="failure.status"
          @feedback="submitFeedback"
          @retry="reanalyse"
        />
      </div>

      <aside class="space-y-5">
        <SimilarFailuresPanel :items="failure.similar_failures" />
        <RecommendationsPanel :items="failure.recommendations" :failure="failure" />
        <FailureMetaPanel :failure="failure" />
      </aside>
    </div>
  </div>
</template>
```

### The observed / analysis split

This is the most important design decision in the product. Two panels, visibly different, never merged.

```vue
<!-- ready — src/components/failure/ObservedPanel.vue -->
<template>
  <PmCard :padded="false">
    <div class="flex items-center gap-2 border-b px-5 py-3">
      <i-lucide-eye class="size-4 text-dim" />
      <h3 class="text-[13px] font-semibold uppercase tracking-wide text-dim">Observed</h3>
      <span class="text-xs text-mute">— facts collected from your pipeline</span>
    </div>

    <div class="space-y-5 p-5">
      <ChangedFilesList :files="observed.changed_files" />
      <PreviousPipelineNote :previous="observed.previous_pipeline" />
      <LogViewer :job-uuid="job.uuid" auto-scroll-to-error />
    </div>
  </PmCard>
</template>
```

```vue
<!-- ready — src/components/failure/AnalysisPanel.vue -->
<script setup lang="ts">
const props = defineProps<{
  analysis: Analysis | null
  status: string
}>()

const confidenceTone = computed(() => {
  const c = props.analysis?.confidence ?? 0
  return c >= 0.85 ? 'var(--pm-accent)' : c >= 0.6 ? 'var(--pm-warning)' : 'var(--pm-text-dim)'
})
</script>

<template>
  <!-- Analysis running: the pipeline already failed; this is a separate, ongoing state. -->
  <PmCard v-if="status === 'analyzing' || status === 'queued'" class="border-[color:var(--pm-ai)]/25">
    <div class="flex items-center gap-3 py-2">
      <i-lucide-loader-circle class="size-5 animate-spin text-[var(--pm-ai)]" />
      <div>
        <p class="text-sm font-medium">PipeMind is analysing this failure…</p>
        <p class="mt-0.5 text-xs text-dim">Usually takes 5–10 seconds.</p>
      </div>
    </div>
  </PmCard>

  <!-- Analysis failed ≠ pipeline failed. Say which one broke. -->
  <PmCard v-else-if="status === 'analysis_failed'" class="border-[color:var(--pm-warning)]/30">
    <div class="flex items-start gap-3 py-1">
      <i-lucide-triangle-alert class="mt-0.5 size-5 text-[var(--pm-warning)]" />
      <div class="flex-1">
        <p class="text-sm font-medium">Analysis could not be completed</p>
        <p class="mt-1 text-xs text-dim">
          The pipeline failure is real — only PipeMind's analysis of it failed.
          The raw log above is unaffected.
        </p>
        <PmButton size="sm" variant="secondary" class="mt-3" @click="$emit('retry')">
          Try again
        </PmButton>
      </div>
    </div>
  </PmCard>

  <PmCard v-else-if="analysis" :padded="false" class="border-[color:var(--pm-ai)]/25">
    <div class="flex items-center justify-between gap-3 border-b px-5 py-3">
      <div class="flex items-center gap-2">
        <i-lucide-sparkles class="size-4 text-[var(--pm-ai)]" />
        <h3 class="text-[13px] font-semibold uppercase tracking-wide text-[var(--pm-ai)]">
          PipeMind Analysis
        </h3>
      </div>
      <ConfidenceBadge :value="analysis.confidence" :tone="confidenceTone" />
    </div>

    <div class="space-y-5 p-5">
      <p class="text-[15px] font-medium leading-relaxed">{{ analysis.summary }}</p>
      <p class="text-sm leading-relaxed text-dim">{{ analysis.root_cause }}</p>

      <details v-if="analysis.explanation" class="group">
        <summary class="cursor-pointer text-xs font-medium text-accent">
          More detail
        </summary>
        <p class="mt-2 whitespace-pre-line text-sm leading-relaxed text-dim">
          {{ analysis.explanation }}
        </p>
      </details>

      <EvidenceList :evidence="analysis.evidence" />

      <PmAlert v-if="analysis.is_transient" tone="info">
        <i-lucide-refresh-cw class="size-4" />
        This looks transient. A retry may succeed without any code change.
      </PmAlert>

      <AnalysisProvenance :analysis="analysis" />
      <AnalysisFeedback :analysis="analysis" @submit="$emit('feedback', $event)" />
    </div>
  </PmCard>

  <PmCard v-else class="text-center">
    <div class="py-6">
      <p class="text-sm text-dim">This failure hasn't been analysed yet.</p>
      <PmButton variant="primary" size="sm" class="mt-3" @click="$emit('retry')">
        Analyse now
      </PmButton>
    </div>
  </PmCard>
</template>
```

```vue
<!-- ready — src/components/failure/ConfidenceBadge.vue -->
<script setup lang="ts">
const props = defineProps<{ value: number, tone: string }>()

// Words, not just a number. "92%" alone invites false precision;
// "High confidence · 92%" tells the reader how much weight to give it.
const label = computed(() =>
  props.value >= 0.85 ? 'High confidence'
  : props.value >= 0.6 ? 'Moderate confidence'
    : 'Low confidence')
</script>

<template>
  <PmTooltip content="How strongly the evidence supports this conclusion. Always check the evidence below.">
    <span class="flex items-center gap-2 text-xs" :style="{ color: tone }">
      <span class="relative grid size-7 place-items-center">
        <svg class="-rotate-90" viewBox="0 0 28 28">
          <circle cx="14" cy="14" r="11" fill="none" stroke="var(--pm-surface-3)" stroke-width="3" />
          <circle
            cx="14" cy="14" r="11" fill="none" :stroke="tone" stroke-width="3" stroke-linecap="round"
            :stroke-dasharray="69.1" :stroke-dashoffset="69.1 * (1 - value)"
          />
        </svg>
      </span>
      <span class="font-medium">{{ label }} · {{ Math.round(value * 100) }}%</span>
    </span>
  </PmTooltip>
</template>
```

```vue
<!-- ready — src/components/failure/EvidenceList.vue -->
<script setup lang="ts">
const EVIDENCE_ICON = {
  log_line: 'i-lucide-terminal',
  changed_file: 'i-lucide-file-diff',
  historical_failure: 'i-lucide-history',
  metric: 'i-lucide-activity',
  config: 'i-lucide-settings-2',
  commit: 'i-lucide-git-commit',
  doc: 'i-lucide-book-open',
} as const
</script>

<template>
  <div>
    <p class="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-mute">Evidence</p>

    <ul class="space-y-1.5">
      <li v-for="(e, i) in evidence" :key="i">
        <!-- Every evidence item links to its source. An unverifiable claim is
             not evidence, and this is what stops the panel being a wall of assertions. -->
        <component
          :is="evidenceLink(e) ? 'RouterLink' : 'div'"
          :to="evidenceLink(e)"
          class="flex items-start gap-2.5 rounded-[var(--pm-radius-sm)] px-2.5 py-2 text-[13px] transition-colors"
          :class="evidenceLink(e) ? 'hover:bg-surface-2' : ''"
        >
          <i :class="EVIDENCE_ICON[e.type]" class="mt-0.5 size-3.5 shrink-0 text-accent" />
          <span class="min-w-0 flex-1 text-dim">{{ e.content }}</span>
          <span v-if="e.source_ref" class="shrink-0 font-mono text-[11px] text-mute">
            {{ formatSourceRef(e) }}
          </span>
        </component>
      </li>
    </ul>
  </div>
</template>
```

```vue
<!-- ready — src/components/failure/AnalysisProvenance.vue -->
<template>
  <!-- Show the machinery. A developer deciding whether to trust this needs to know
       whether history informed it and which model produced it. -->
  <div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-3 text-[11px] text-mute">
    <PmTooltip :content="SOURCE_EXPLAIN[analysis.classification_source]">
      <span class="flex items-center gap-1">
        <i-lucide-cpu class="size-3" />{{ analysis.classification_source }}
      </span>
    </PmTooltip>

    <PmTooltip v-if="analysis.used_rag"
               :content="`Informed by ${analysis.similar_failures_count} similar past failures`">
      <span class="flex items-center gap-1 text-accent">
        <i-lucide-history class="size-3" />history
      </span>
    </PmTooltip>

    <span>{{ analysis.model_name }}</span>
    <span>{{ (analysis.latency_ms! / 1000).toFixed(1) }}s</span>
    <span>{{ cost(analysis.cost_usd) }}</span>

    <PmBadge v-if="analysis.cache_hit" tone="dim">cached</PmBadge>
  </div>
</template>
```

- [ ] `ObservedPanel`, `AnalysisPanel`, `EvidenceList`, `ConfidenceBadge`, `AnalysisProvenance`, `AnalysisFeedback` built
- [ ] Observed and Analysis are visually distinct — different border tone, different header treatment
- [ ] Every evidence item with a `source_ref` links to something real

---

## 16.5 Similar failures & recommendations

```vue
<!-- ready — src/components/failure/SimilarFailureItem.vue -->
<template>
  <RouterLink
    :to="{ name: 'project.failure', params: { slug, uuid: item.uuid } }"
    class="block rounded-[var(--pm-radius)] border p-3 transition-colors hover:bg-surface-2"
  >
    <div class="flex items-center justify-between gap-2">
      <span class="flex items-center gap-2">
        <SimilarityRing :value="item.similarity" />
        <span class="text-[13px] font-medium">{{ Math.round(item.similarity * 100) }}% similar</span>
      </span>
      <span class="text-[11px] text-mute">{{ relative(item.occurred_at) }}</span>
    </div>

    <p v-if="item.root_cause" class="mt-2 line-clamp-2 text-xs text-dim">{{ item.root_cause }}</p>

    <!-- A resolved neighbour is the useful one. Make that obvious at a glance. -->
    <p v-if="item.resolved" class="mt-2 flex items-start gap-1.5 text-xs text-accent">
      <i-lucide-check class="mt-0.5 size-3 shrink-0" />
      <span class="line-clamp-2">Fixed by: {{ item.resolution }}</span>
    </p>
    <p v-else class="mt-2 text-xs text-mute">Never resolved</p>
  </RouterLink>
</template>
```

```vue
<!-- ready — src/components/failure/RecommendationCard.vue -->
<template>
  <div class="rounded-[var(--pm-radius)] border p-4">
    <div class="flex items-start justify-between gap-2">
      <h4 class="text-[13px] font-semibold leading-snug">{{ rec.title }}</h4>
      <RiskBadge :risk="rec.risk" />
    </div>

    <p class="mt-2 text-xs leading-relaxed text-dim">{{ rec.description }}</p>

    <p v-if="rec.rationale" class="mt-2 border-l-2 pl-2.5 text-xs italic text-mute">
      {{ rec.rationale }}
    </p>

    <ul v-if="rec.affected_files.length" class="mt-2.5 space-y-1">
      <li v-for="f in rec.affected_files" :key="f" class="flex items-center gap-1.5 font-mono text-[11px] text-dim">
        <i-lucide-file class="size-3" />{{ f }}
      </li>
    </ul>

    <!-- The policy decision is rendered, not hidden. The user sees the gate before
         they click, rather than discovering it in an error toast afterwards. -->
    <PolicyNotice :policy="rec.policy" class="mt-3" />

    <div class="mt-3 flex gap-2">
      <PmButton v-if="rec.has_patch" size="sm" variant="secondary" @click="$emit('review')">
        Review fix
      </PmButton>

      <PmButton
        v-if="rec.policy.decision !== 'forbidden' && auth.can('remediation.request')"
        size="sm" variant="primary" @click="$emit('apply')"
      >
        {{ rec.policy.decision === 'auto_allowed' ? 'Apply' : 'Request approval' }}
      </PmButton>

      <PmButton size="sm" variant="ghost" @click="$emit('reject')">Dismiss</PmButton>
    </div>
  </div>
</template>
```

- [ ] Similar failures and recommendation panels built
- [ ] Patch review opens a diff modal (`RecommendationPatchModal`)

---

## 16.6 Failures list & history

| Route | View | Notes |
|---|---|---|
| `/app/projects/:slug/failures` | `FailuresView` | Grouped by signature by default — the same error 12 times is one row, not twelve |
| `/app/projects/:slug/analyses` | `AnalysesView` | All analyses with confidence, cost, feedback status |
| `/app/projects/:slug/history` | `FailureHistoryView` | Signature catalogue: occurrences, first/last seen, known resolution |

> **Group the failures list by signature.** An ungrouped list after a bad week is forty rows of the same three problems. Grouped, it is three rows with counts — which is the actual shape of the information and the view that makes recurring problems obvious.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ ⚠ DATABASE · Connection refused                    4 occurrences    │
│   SQLSTATE[HY000] [2002] Connection refused                         │
│   First seen 3 days ago · last 2 min ago · ✓ known fix available    │
│   ▸ #821 2m ago  ▸ #814 1d ago  ▸ #802 2d ago  ▸ #799 3d ago        │
├─────────────────────────────────────────────────────────────────────┤
│ ⚠ DEPENDENCY · Version conflict                    1 occurrence     │
└─────────────────────────────────────────────────────────────────────┘
```

- [ ] Three views built, grouping toggle persists

---

## Definition of Done — **M3 UI** ⭐

Full loop, visible:

```bash
# 1. everything running (compose, horizon, ai, front)
# 2. break the lab: FAIL_MODE=database
# 3. watch the browser
```

- [ ] The pipeline appears on the project board within ~10 s
- [ ] Clicking the failed row lands on the failure page
- [ ] The analysis appears live, without a manual refresh
- [ ] **Observed** and **Analysis** are unmistakably different panels
- [ ] Every evidence item links to a real log line, file, or past failure
- [ ] The log viewer opens on the excerpt, scrolled to line 1294, redaction badge showing
- [ ] Confidence renders as words plus a number, with a tooltip explaining it
- [ ] Provenance shows classification source, RAG usage, model, latency, cost
- [ ] Killing the AI container shows "Analysis could not be completed" — and the pipeline still reads as failed, not broken
- [ ] Thumbs-down opens the correction form and posts to `/analyses/{a}/feedback`
- [ ] A 48,000-line log scrolls at 60 fps

**Next:** [`17-realtime.md`](17-realtime.md)
