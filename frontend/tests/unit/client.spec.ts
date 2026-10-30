import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiError, readStoredToken, storeToken } from '@/api/client'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 每次调用都返回一个全新的 Response —— Response body 只能读取一次。 */
function responder(body: unknown, status = 200) {
  return vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(body, status)))
}

describe('ApiClient', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('拼接查询参数并忽略空值', async () => {
    const fetchMock = responder({ entries: [], tags: [], total: 0 })
    const client = new ApiClient({
      fetchImpl: fetchMock as unknown as typeof fetch,
      tokenProvider: () => '',
    })

    await client.catalog({ tags: ['ops', 'media'], search: '', matchAll: true })

    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/catalog?')
    expect(url).toContain('tags=ops%2Cmedia')
    expect(url).toContain('match_all=true')
    expect(url).not.toContain('search')
  })

  it('携带 token 请求头', async () => {
    const fetchMock = responder({ ok: true })
    const client = new ApiClient({
      fetchImpl: fetchMock as unknown as typeof fetch,
      tokenProvider: () => 'secret-token',
    })

    await client.health()

    const init = fetchMock.mock.calls[0][1] as RequestInit
    const headers = new Headers(init.headers)
    expect(headers.get('X-LightPanel-Token')).toBe('secret-token')
  })

  it('写入类请求自动带上 JSON 内容类型与序列化体', async () => {
    const fetchMock = responder({ id: 'x' }, 201)
    const client = new ApiClient({
      fetchImpl: fetchMock as unknown as typeof fetch,
      tokenProvider: () => '',
    })

    await client.createEntry({ name: 'Test', tags: ['a'] })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(String(init.body))).toEqual({ name: 'Test', tags: ['a'] })
  })

  it('非 2xx 响应抛出的 ApiError 保留状态码与业务错误码', async () => {
    const fetchMock = responder({ code: 'not_found', message: '条目不存在' }, 404)
    const client = new ApiClient({
      fetchImpl: fetchMock as unknown as typeof fetch,
      tokenProvider: () => '',
    })

    await expect(client.container('missing')).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
    })
    await expect(client.container('missing')).rejects.toBeInstanceOf(ApiError)
  })

  it('204 响应解析为 undefined 而不报错', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    const client = new ApiClient({
      fetchImpl: fetchMock as unknown as typeof fetch,
      tokenProvider: () => '',
    })

    await expect(client.deleteEntry('x')).resolves.toBeUndefined()
  })

  it('容器与编排操作映射到正确的 REST 路径', async () => {
    const fetchMock = responder({})
    const client = new ApiClient({
      fetchImpl: fetchMock as unknown as typeof fetch,
      tokenProvider: () => '',
    })

    await client.containerAction('web/nginx', 'restart')
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain('/containers/web%2Fnginx/restart')

    await client.stackAction('blog', 'up', ['-d'])
    const stackCall = fetchMock.mock.calls.at(-1) as [string, RequestInit]
    expect(String(stackCall[0])).toContain('/stacks/blog/up')
    expect(JSON.parse(String(stackCall[1].body))).toEqual({ extra_args: ['-d'] })
  })

  it('命令执行带上 target_id 与超时', async () => {
    const fetchMock = responder({ ok: true })
    const client = new ApiClient({
      fetchImpl: fetchMock as unknown as typeof fetch,
      tokenProvider: () => '',
    })

    await client.runCommand('container.logs', { targetId: 'nginx', extraArgs: ['-f'], timeout: 5 })

    const call = fetchMock.mock.calls.at(-1) as [string, RequestInit]
    expect(String(call[0])).toContain('/commands/container.logs/run')
    expect(JSON.parse(String(call[1].body))).toEqual({
      target_id: 'nginx',
      extra_args: ['-f'],
      timeout: 5,
    })
  })
})

describe('token 存储', () => {
  it('写入后可读取，清空后消失', () => {
    storeToken('abc')
    expect(readStoredToken()).toBe('abc')
    expect(localStorage.getItem('lightpanel.token')).toBe('abc')
    storeToken('')
    expect(readStoredToken()).toBe('')
  })
})
