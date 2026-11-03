/** 极薄的一层 fetch 封装：统一前缀、鉴权头与错误归一化。 */

import type {
  ApiErrorBody,
  AuthStatus,
  CatalogPage,
  CatalogQueryParams,
  CommandDefinition,
  CommandPreview,
  CommandResult,
  CommandTarget,
  ContainerActionResult,
  ContainerInfo,
  ContainerUsagePage,
  EngineStatus,
  HealthStatus,
  LogsPayload,
  MetricSample,
  SoftwareEntry,
  StackActionResult,
  StackInfo,
  SystemSnapshot,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, body: Partial<ApiErrorBody>) {
    super(body.message ?? `请求失败 (HTTP ${status})`)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code ?? 'http_error'
    this.details = body.details ?? {}
  }
}

export interface ApiClientOptions {
  baseUrl?: string
  /** 返回当前 token；未启用鉴权时返回空串即可。 */
  tokenProvider?: () => string
  fetchImpl?: typeof fetch
}

const TOKEN_STORAGE_KEY = 'lightpanel.token'

export class ApiClient {
  readonly baseUrl: string
  private readonly tokenProvider: () => string
  private readonly fetchImpl: typeof fetch

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '/api'
    this.tokenProvider = options.tokenProvider ?? (() => readStoredToken())
    this.fetchImpl =
      options.fetchImpl ??
      (typeof fetch === 'function' ? fetch.bind(globalThis) : fallbackFetch)
  }

  private async request<T>(
    path: string,
    init: RequestInit & { query?: Record<string, unknown> } = {},
  ): Promise<T> {
    const { query, ...rest } = init
    const url = this.buildUrl(path, query)
    const headers = new Headers(rest.headers ?? {})
    if (rest.body !== undefined && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    const token = this.tokenProvider()
    if (token) headers.set('X-LightPanel-Token', token)

    const response = await this.fetchImpl(url, { ...rest, headers })
    if (!response.ok) {
      throw new ApiError(response.status, await safeJson<Partial<ApiErrorBody>>(response))
    }
    if (response.status === 204) return undefined as T
    return (await safeJson<T>(response)) as T
  }

  private buildUrl(path: string, query?: Record<string, unknown>): string {
    const base = `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`
    if (!query) return base
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue
      if (Array.isArray(value)) {
        if (value.length) search.set(key, value.join(','))
      } else {
        search.set(key, String(value))
      }
    }
    const qs = search.toString()
    return qs ? `${base}?${qs}` : base
  }

  // -- meta ------------------------------------------------------------------
  health(): Promise<HealthStatus> {
    return this.request('/health')
  }

  authStatus(): Promise<AuthStatus> {
    return this.request('/auth/status')
  }

  login(token: string): Promise<AuthStatus> {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ token }),
    })
  }

  changePassword(current: string, next: string): Promise<AuthStatus> {
    return this.request('/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current, new: next }),
    })
  }

  // -- system ----------------------------------------------------------------
  system(): Promise<SystemSnapshot> {
    return this.request('/system')
  }

  systemHistory(): Promise<MetricSample[]> {
    return this.request('/system/history')
  }

  invalidateSystem(): Promise<{ ok: boolean }> {
    return this.request('/system/invalidate', { method: 'POST' })
  }

  dockerStatus(): Promise<EngineStatus> {
    return this.request('/containers/status')
  }

  // -- catalog ---------------------------------------------------------------
  catalog(params: CatalogQueryParams = {}): Promise<CatalogPage> {
    return this.request('/catalog', {
      query: {
        tags: params.tags ?? [],
        match_all: params.matchAll ? 'true' : '',
        category: params.category ?? '',
        search: params.search ?? '',
        enabled_only: params.enabledOnly ? 'true' : '',
        sort: params.sort ?? '',
      },
    })
  }

  createEntry(payload: Partial<SoftwareEntry>): Promise<SoftwareEntry> {
    return this.request('/catalog/entries', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  updateEntry(id: string, payload: Partial<SoftwareEntry>): Promise<SoftwareEntry> {
    return this.request(`/catalog/entries/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  }

  deleteEntry(id: string): Promise<{ ok: boolean }> {
    return this.request(`/catalog/entries/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }

  updateTags(id: string, tags: string[]): Promise<SoftwareEntry> {
    return this.request(`/catalog/entries/${encodeURIComponent(id)}/tags`, {
      method: 'PUT',
      body: JSON.stringify({ tags }),
    })
  }

  reorderEntries(ids: string[]): Promise<SoftwareEntry[]> {
    return this.request('/catalog/reorder', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    })
  }

  // -- containers ------------------------------------------------------------
  containers(params: { includeStopped?: boolean; search?: string; project?: string; state?: string } = {}): Promise<ContainerInfo[]> {
    return this.request('/containers', {
      query: {
        include_stopped: params.includeStopped === false ? 'false' : '',
        search: params.search ?? '',
        project: params.project ?? '',
        state: params.state ?? '',
      },
    })
  }

  /** 运行中容器的 CPU / 内存快照（服务端缓存 5s）。 */
  containerUsage(): Promise<ContainerUsagePage> {
    return this.request('/containers/usage')
  }

  container(id: string): Promise<ContainerInfo> {
    return this.request(`/containers/${encodeURIComponent(id)}`)
  }

  containerAction(
    id: string,
    action: 'start' | 'stop' | 'restart' | 'pause' | 'unpause' | 'remove',
    timeout?: number,
  ): Promise<ContainerActionResult> {
    return this.request(`/containers/${encodeURIComponent(id)}/${action}`, {
      method: 'POST',
      body: JSON.stringify(timeout === undefined ? {} : { timeout }),
    })
  }

  containerLogs(id: string, tail = 200): Promise<LogsPayload> {
    return this.request(`/containers/${encodeURIComponent(id)}/logs`, {
      query: { tail },
    })
  }

  // -- stacks ----------------------------------------------------------------
  stacks(): Promise<StackInfo[]> {
    return this.request('/stacks')
  }

  stack(name: string): Promise<StackInfo> {
    return this.request(`/stacks/${encodeURIComponent(name)}`)
  }

  stackAction(
    name: string,
    action: 'up' | 'down' | 'restart' | 'stop' | 'pull' | 'build',
    extraArgs: string[] = [],
  ): Promise<StackActionResult> {
    return this.request(`/stacks/${encodeURIComponent(name)}/${action}`, {
      method: 'POST',
      body: JSON.stringify({ extra_args: extraArgs }),
    })
  }

  // -- commands --------------------------------------------------------------
  commands(target?: CommandTarget): Promise<CommandDefinition[]> {
    return this.request('/commands', { query: { target: target ?? '' } })
  }

  previewCommand(id: string, targetId: string, extraArgs: string[] = []): Promise<CommandPreview> {
    return this.request(`/commands/${encodeURIComponent(id)}/preview`, {
      method: 'POST',
      body: JSON.stringify({ target_id: targetId, extra_args: extraArgs }),
    })
  }

  runCommand(
    id: string,
    payload: { targetId?: string; extraArgs?: string[]; timeout?: number } = {},
  ): Promise<CommandResult> {
    return this.request(`/commands/${encodeURIComponent(id)}/run`, {
      method: 'POST',
      body: JSON.stringify({
        target_id: payload.targetId ?? null,
        extra_args: payload.extraArgs ?? [],
        timeout: payload.timeout ?? null,
      }),
    })
  }

  runAdHoc(payload: {
    argv: string[]
    cwd?: string | null
    timeout?: number | null
    context?: Record<string, unknown>
  }): Promise<CommandResult> {
    return this.request('/commands/run-adhoc', {
      method: 'POST',
      body: JSON.stringify({
        argv: payload.argv,
        cwd: payload.cwd ?? null,
        timeout: payload.timeout ?? null,
        context: payload.context ?? {},
      }),
    })
  }
}

export function readStoredToken(): string {
  try {
    return globalThis.localStorage?.getItem(TOKEN_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function storeToken(token: string): void {
  try {
    if (token) globalThis.localStorage?.setItem(TOKEN_STORAGE_KEY, token)
    else globalThis.localStorage?.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    /* 忽略：隐私模式下 localStorage 不可用 */
  }
}

async function safeJson<T>(response: Response): Promise<T | Partial<ApiErrorBody>> {
  const text = await response.text()
  if (!text) return {} as T
  try {
    return JSON.parse(text) as T
  } catch {
    return { message: text } as unknown as Partial<ApiErrorBody>
  }
}

/** SSR / 测试环境下没有真实 fetch 时的兜底，避免直接崩溃。 */
function fallbackFetch(): Promise<Response> {
  return Promise.reject(new ApiError(0, { code: 'no_fetch', message: '当前环境不支持 fetch' }))
}

export const api = new ApiClient()
