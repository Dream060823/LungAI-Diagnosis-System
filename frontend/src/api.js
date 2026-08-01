const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim()
export const API_BASE = configuredBase ? configuredBase.replace(/\/$/, '') : ''

export async function apiRequest(path, options = {}) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 30_000)

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
    })

    const type = response.headers.get('content-type') || ''
    const body = type.includes('application/json')
      ? await response.json()
      : await response.text()

    if (!response.ok) {
      const message = typeof body === 'object' ? body.error || body.message : body
      throw new Error(message || `请求失败（${response.status}）`)
    }

    return body
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('请求超时，请确认后端服务是否正常运行')
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}
