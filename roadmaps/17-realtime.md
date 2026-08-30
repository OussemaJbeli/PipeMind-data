# 17 — Real-Time

**Repo:** `PipeMind-back` + `PipeMind-front` · **Depends on:** 16 · **Milestone:** M5

Live pipeline, job and analysis updates over WebSockets. Replaces most polling; polling stays as the fallback.

---

## 17.1 Laravel Reverb

Reverb is first-party, runs in your own compose stack, and needs no external service.

```bash
# ready
composer require laravel/reverb
php artisan reverb:install
```

```bash
# ready — .env additions
BROADCAST_CONNECTION=reverb
REVERB_APP_ID=pipemind
REVERB_APP_KEY=pipemind-key
REVERB_APP_SECRET=change-me
REVERB_HOST=localhost
REVERB_PORT=8080
REVERB_SCHEME=http
```

```yaml
# ready — append to docker-compose.yml
  reverb:
    build: .
    container_name: pipemind-reverb
    restart: unless-stopped
    command: php artisan reverb:start --host=0.0.0.0 --port=8080
    ports: ["8080:8080"]
    env_file: .env
    depends_on:
      redis: { condition: service_healthy }
    networks: [pipemind]
```

- [ ] Reverb installed and running

---

## 17.2 Channels

Everything is a **private** channel authorised against team membership.

```php
// ready — routes/channels.php
Broadcast::channel('team.{teamUuid}', function ($user, string $teamUuid) {
    return $user->teams()->where('teams.uuid', $teamUuid)->exists();
});

Broadcast::channel('project.{projectUuid}', function ($user, string $projectUuid) {
    return Project::where('uuid', $projectUuid)
        ->whereIn('team_id', $user->teams()->pluck('teams.id'))
        ->exists();
});

Broadcast::channel('pipeline.{pipelineUuid}', function ($user, string $pipelineUuid) {
    return Pipeline::where('pipelines.uuid', $pipelineUuid)
        ->join('projects', 'projects.id', '=', 'pipelines.project_id')
        ->whereIn('projects.team_id', $user->teams()->pluck('teams.id'))
        ->exists();
});
```

> **Never use public channels here.** Pipeline names, branch names and log excerpts are proprietary. A public channel broadcasts them to anyone who guesses a UUID.

| Channel | Events |
|---|---|
| `team.{uuid}` | `activity.created`, `notification.created`, `remediation.pending` |
| `project.{uuid}` | `pipeline.updated`, `failure.detected`, `analysis.completed`, `anomaly.detected`, `stats.updated` |
| `pipeline.{uuid}` | `job.updated`, `pipeline.updated` |

---

## 17.3 Events

```php
// ready — app/Events/PipelineUpdated.php
class PipelineUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public function __construct(public Pipeline $pipeline) {}

    public function broadcastOn(): array
    {
        return [
            new PrivateChannel("project.{$this->pipeline->project->uuid}"),
            new PrivateChannel("pipeline.{$this->pipeline->uuid}"),
        ];
    }

    public function broadcastAs(): string
    {
        return 'pipeline.updated';
    }

    /** Broadcast a small, complete payload — never a partial that forces a refetch. */
    public function broadcastWith(): array
    {
        return [
            'uuid'             => $this->pipeline->uuid,
            'iid'              => $this->pipeline->iid,
            'status'           => $this->pipeline->status,
            'ref'              => $this->pipeline->ref,
            'duration_seconds' => $this->pipeline->duration_seconds,
            'finished_at'      => $this->pipeline->finished_at?->toIso8601String(),
            'jobs_failed'      => $this->pipeline->jobs_failed,
            'has_failure'      => $this->pipeline->has_failure,
        ];
    }
}
```

Events to implement: `PipelineUpdated`, `JobUpdated`, `FailureDetected`, `AnalysisStarted`, `AnalysisCompleted`, `AnomalyDetected`, `RemediationStatusChanged`, `ActivityCreated`, `ProjectStatsUpdated`.

**All broadcasting goes through the queue** (`ShouldBroadcast`, not `ShouldBroadcastNow`) so a slow WebSocket never blocks ingestion.

- [ ] Nine events implemented, dispatched from the jobs in files 05 and 10

---

## 17.4 Frontend

```ts
// ready — src/composables/useEcho.ts
import Echo from 'laravel-echo'
import Pusher from 'pusher-js'

let echo: Echo | null = null

export function useEcho() {
  if (!echo) {
    window.Pusher = Pusher
    echo = new Echo({
      broadcaster: 'reverb',
      key: import.meta.env.VITE_REVERB_KEY,
      wsHost: import.meta.env.VITE_WS_HOST,
      wsPort: Number(import.meta.env.VITE_WS_PORT),
      forceTLS: import.meta.env.VITE_WS_SCHEME === 'https',
      enabledTransports: ['ws', 'wss'],
      authEndpoint: '/broadcasting/auth',
      withCredentials: true,
    })
  }
  return echo
}

/** Subscribe for the lifetime of a component. Always leaves on unmount. */
export function useChannel(name: MaybeRefOrGetter<string | null>, handlers: Record<string, (e: any) => void>) {
  let current: string | null = null

  const attach = (channel: string) => {
    const ch = useEcho().private(channel)
    for (const [event, fn] of Object.entries(handlers))
      ch.listen(`.${event}`, fn)
    current = channel
  }

  watchEffect(() => {
    const next = toValue(name)
    if (current === next) return
    if (current) useEcho().leave(current)
    if (next) attach(next)
  })

  onScopeDispose(() => { if (current) useEcho().leave(current) })
}
```

```ts
// ready — src/composables/useProjectRealtime.ts
export function useProjectRealtime(projectUuid: MaybeRef<string | undefined>) {
  const qc = useQueryClient()

  useChannel(() => unref(projectUuid) ? `project.${unref(projectUuid)}` : null, {
    'pipeline.updated': (e) => {
      // Patch the cache directly rather than invalidating: the payload is complete,
      // and a refetch on every job event would hammer the API during a busy pipeline.
      qc.setQueriesData({ queryKey: ['pipelines'] }, (old: any) =>
        old ? patchPipeline(old, e) : old)

      if (['success', 'failed', 'canceled'].includes(e.status))
        qc.invalidateQueries({ queryKey: ['project', 'overview'] })
    },

    'failure.detected': (e) => {
      qc.invalidateQueries({ queryKey: ['project', 'overview'] })
      toast.error(`Pipeline #${e.pipeline_iid} failed`, {
        description: e.error_message,
        action: { label: 'Investigate', onClick: () => router.push(failureRoute(e)) },
      })
    },

    'analysis.completed': (e) => {
      qc.setQueryData(['failure', e.failure_uuid], (old: any) =>
        old ? { ...old, status: 'analyzed', analysis: e.analysis } : old)
      qc.invalidateQueries({ queryKey: ['failure', e.failure_uuid] })
    },

    'anomaly.detected': e => toast.warning(e.title, { description: e.description }),
  })
}
```

**Reconnection and degradation:**

```ts
// ready — src/composables/useConnectionStatus.ts
// Echo drops on network loss. The UI must say so, and polling must resume.
export function useConnectionStatus() {
  const state = ref<'connected' | 'connecting' | 'disconnected'>('connecting')

  const pusher = useEcho().connector.pusher
  pusher.connection.bind('connected', () => { state.value = 'connected' })
  pusher.connection.bind('connecting', () => { state.value = 'connecting' })
  pusher.connection.bind('unavailable', () => { state.value = 'disconnected' })
  pusher.connection.bind('failed', () => { state.value = 'disconnected' })

  return { state, isLive: computed(() => state.value === 'connected') }
}
```

- When disconnected: show a small "Reconnecting — showing cached data" bar and **re-enable polling intervals**.
- On reconnect: invalidate all queries once. Events missed while offline are gone; a single refetch resynchronises.

> **Realtime is an optimisation, never the only path.** Every screen must remain correct with WebSockets disabled entirely — that is what makes the fallback trustworthy and what lets you ship the frontend before Reverb exists.

- [ ] `useEcho`, `useChannel`, `useProjectRealtime`, `useConnectionStatus` built
- [ ] Polling intervals disable while `isLive`, re-enable on disconnect
- [ ] Connection indicator in the topbar

---

## Definition of Done

- [ ] Trigger a pipeline: rows update live with no refresh, no polling requests in the network tab
- [ ] Analysis appears on the failure page the moment it completes
- [ ] Toast on failure detection routes to the failure
- [ ] Kill Reverb: UI shows "Reconnecting", polling resumes, data stays correct
- [ ] Restart Reverb: reconnects and resynchronises within 10 s
- [ ] Two browser tabs stay in sync
- [ ] Leaving a project page unsubscribes (verify in the Reverb log)

**Next:** [`18-remediation.md`](18-remediation.md)
