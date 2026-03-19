/**
 * FinAgent API client — typed fetch wrapper.
 * All requests go through here so auth headers are automatic.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ─── Token management ─────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('finagent_token')
}

export function setTokens(access: string, refresh: string, tenantId: string, name: string) {
  localStorage.setItem('finagent_token', access)
  localStorage.setItem('finagent_refresh', refresh)
  localStorage.setItem('finagent_tenant_id', tenantId)
  localStorage.setItem('finagent_name', name)
}

export function clearTokens() {
  localStorage.removeItem('finagent_token')
  localStorage.removeItem('finagent_refresh')
  localStorage.removeItem('finagent_tenant_id')
  localStorage.removeItem('finagent_name')
}

export function isAuthenticated(): boolean {
  return !!getToken()
}

export function getUserName(): string {
  return localStorage.getItem('finagent_name') || 'Usuário'
}

// ─── Base fetch ────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  auth = true
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }

  if (auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    // Try to refresh token
    const refreshed = await tryRefreshToken()
    if (refreshed) {
      // Retry with new token
      headers['Authorization'] = `Bearer ${getToken()}`
      const retryRes = await fetch(`${API_BASE}${path}`, { ...options, headers })
      if (!retryRes.ok) throw new ApiError(retryRes.status, await retryRes.json())
      return retryRes.json()
    } else {
      clearTokens()
      window.location.href = '/login'
      throw new ApiError(401, { detail: 'Session expired' })
    }
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new ApiError(res.status, errorData)
  }

  if (res.status === 204) return {} as T
  return res.json()
}

async function tryRefreshToken(): Promise<boolean> {
  const refresh = localStorage.getItem('finagent_refresh')
  if (!refresh) return false
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })
    if (!res.ok) return false
    const data = await res.json()
    setTokens(data.access_token, data.refresh_token, data.tenant_id, data.name)
    return true
  } catch {
    return false
  }
}

export class ApiError extends Error {
  status: number
  data: unknown
  constructor(status: number, data: unknown) {
    const message = (data as { detail?: string })?.detail || `HTTP ${status}`
    super(message)
    this.status = status
    this.data = data
  }
}

// ─── Auth ──────────────────────────────────────────────────────────────────

export const auth = {
  async register(body: { name: string; email: string; password: string; business_name?: string }) {
    const data = await apiFetch<{ access_token: string; refresh_token: string; tenant_id: string; name: string }>(
      '/api/v1/auth/register', { method: 'POST', body: JSON.stringify(body) }, false
    )
    setTokens(data.access_token, data.refresh_token, data.tenant_id, data.name)
    return data
  },

  async login(email: string, password: string) {
    const data = await apiFetch<{ access_token: string; refresh_token: string; tenant_id: string; name: string }>(
      '/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }, false
    )
    setTokens(data.access_token, data.refresh_token, data.tenant_id, data.name)
    return data
  },

  logout() {
    clearTokens()
    window.location.href = '/login'
  },
}

// ─── Profile ──────────────────────────────────────────────────────────────

export const profile = {
  get: () => apiFetch<Record<string, unknown>>('/api/v1/profile'),
  update: (body: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>('/api/v1/profile', { method: 'PUT', body: JSON.stringify(body) }),
}

// ─── Dashboard / Reports ──────────────────────────────────────────────────

export const reports = {
  summary: (month?: number, year?: number) => {
    const params = new URLSearchParams()
    if (month) params.set('month', String(month))
    if (year) params.set('year', String(year))
    return apiFetch<Record<string, unknown>>(`/api/v1/reports/summary?${params}`)
  },
  cashFlow: (months = 6) =>
    apiFetch<{ cash_flow: Array<Record<string, unknown>> }>(`/api/v1/reports/cash-flow?months=${months}`),
  byCategory: (start?: string, end?: string, type = 'expense') => {
    const params = new URLSearchParams({ type })
    if (start) params.set('start_date', start)
    if (end) params.set('end_date', end)
    return apiFetch<Record<string, unknown>>(`/api/v1/reports/by-category?${params}`)
  },
  list: () => apiFetch<{ reports: Array<Record<string, unknown>> }>('/api/v1/reports'),
}

// ─── Transactions ─────────────────────────────────────────────────────────

export const transactions = {
  list: (params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined) q.set(k, String(v)) })
    return apiFetch<{ items: Array<Record<string, unknown>>; total: number }>(`/api/v1/transactions?${q}`)
  },
  create: (body: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>('/api/v1/transactions', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`/api/v1/transactions/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (id: string) =>
    apiFetch<void>(`/api/v1/transactions/${id}`, { method: 'DELETE' }),
}

// ─── Accounts ─────────────────────────────────────────────────────────────

export const accounts = {
  list: () => apiFetch<{ accounts: Array<Record<string, unknown>>; total_balance: number }>('/api/v1/accounts'),
  create: (body: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>('/api/v1/accounts', { method: 'POST', body: JSON.stringify(body) }),
}

// ─── Alerts ───────────────────────────────────────────────────────────────

export const alerts = {
  list: () => apiFetch<{ alerts: Array<Record<string, unknown>> }>('/api/v1/alerts'),
  create: (body: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>('/api/v1/alerts', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`/api/v1/alerts/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (id: string) =>
    apiFetch<void>(`/api/v1/alerts/${id}`, { method: 'DELETE' }),
}

// ─── Documents ────────────────────────────────────────────────────────────

export const documents = {
  list: () => apiFetch<{ documents: Array<Record<string, unknown>> }>('/api/v1/documents'),
  upload: async (file: File) => {
    const token = getToken()
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/api/v1/documents/upload`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    })
    if (!res.ok) throw new ApiError(res.status, await res.json())
    return res.json()
  },
  confirm: (body: { import_id: string; account_id?: string; skip_duplicates?: boolean }) =>
    apiFetch<Record<string, unknown>>('/api/v1/documents/confirm', { method: 'POST', body: JSON.stringify(body) }),
}

// ─── Chat ─────────────────────────────────────────────────────────────────

export const chat = {
  sendMessage: (message: string, session_id?: string) =>
    apiFetch<{ response: string; session_id: string }>('/api/v1/chat/message', {
      method: 'POST',
      body: JSON.stringify({ message, session_id }),
    }),

  createWebSocket: (): WebSocket | null => {
    const token = getToken()
    if (!token) return null
    const wsBase = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://')
    return new WebSocket(`${wsBase}/api/v1/chat/ws?token=${token}`)
  },
}
