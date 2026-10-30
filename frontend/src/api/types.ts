/** 与后端 `lightpanel.api.schemas` 一一对应的传输类型。 */

export interface HostInfo {
  hostname: string
  os_name: string
  os_version: string
  arch: string
  boot_time: number
  uptime_seconds: number
  uptime_human: string
}

export interface CpuInfo {
  percent: number
  logical_count: number
  physical_count: number | null
  per_cpu: number[]
  load_average: number[] | null
  frequency_mhz: number | null
}

export interface MemoryInfo {
  total: number
  used: number
  available: number
  percent: number
  total_human: string
  used_human: string
  swap_total: number
  swap_used: number
  swap_percent: number
}

export interface DiskInfo {
  device: string
  mountpoint: string
  fstype: string
  total: number
  used: number
  free: number
  percent: number
  total_human: string
  used_human: string
}

export interface NetworkInfo {
  bytes_sent: number
  bytes_recv: number
  packets_sent: number
  packets_recv: number
  interfaces: Record<string, Record<string, number>>
}

export interface SystemSnapshot {
  host: HostInfo
  cpu: CpuInfo
  memory: MemoryInfo
  disks: DiskInfo[]
  network: NetworkInfo | null
  collected_at: string | null
}

export interface MetricSample {
  timestamp: string
  cpu_percent: number
  memory_percent: number
}

export interface EngineStatus {
  provider: string
  available: boolean
  total: number
  running: number
  stopped: number
}

export interface SoftwareEntry {
  id: string
  name: string
  url: string
  description: string
  icon: string
  color: string
  category: string
  tags: string[]
  enabled: boolean
  order: number
}

export interface TagSummary {
  name: string
  count: number
}

export interface CatalogPage {
  entries: SoftwareEntry[]
  tags: TagSummary[]
  total: number
}

export interface ContainerInfo {
  id: string
  short_id: string
  name: string
  image: string
  state: string
  status: string
  created_at: string | null
  ports: string[]
  labels: Record<string, string>
  compose_project: string
  compose_service: string
}

export interface StackInfo {
  name: string
  config_files: string
  working_dir: string
  status: string
  discovered_paths: string[]
  containers: ContainerInfo[]
  running: number
  total: number
}

export interface CommandResult {
  ok: boolean
  exit_code: number
  argv: string[]
  stdout: string
  stderr: string
  duration_ms: number
}

export type CommandTarget = 'container' | 'stack' | 'system'
export type CommandKind = 'lifecycle' | 'shell' | 'compose'

export interface CommandDefinition {
  id: string
  name: string
  target: CommandTarget
  kind: CommandKind
  action: string
  argv: string[]
  description: string
  confirm: boolean
  danger: boolean
  timeout: number
  working_dir: string | null
  builtin: boolean
}

export interface ContainerActionResult {
  container: ContainerInfo
  result: CommandResult
}

export interface StackActionResult {
  stack: StackInfo
  result: CommandResult
}

export interface CommandPreview {
  id: string
  argv: string[]
}

export interface AuthStatus {
  enabled: boolean
  authenticated: boolean
}

export interface HealthStatus {
  status: string
  version: string
  env: string
}

export interface LogsPayload {
  container: string
  tail: number
  content: string
}

/** 统一错误响应体。 */
export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown>
}

export interface CatalogQueryParams {
  tags?: string[]
  matchAll?: boolean
  category?: string
  search?: string
  enabledOnly?: boolean
  sort?: 'order' | 'name' | 'recent'
}
