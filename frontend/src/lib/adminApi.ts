/**
 * Admin API client — separate from the regular client API.
 * Uses X-Admin-Key header instead of JWT.
 *
 * Auth key is stored in localStorage under 'finagent_admin_key'.
 * Login page: /admin/login
 * All admin routes require X-Admin-Key header.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ─── Key management ──────────────────────────────────────────────────────────

export function getAdminKey(): string {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem('finagent_admin_key') || ''
}

export function setAdminKey(key: string) {
  localStorage.setItem('finagent_admin_key', key)
}

export function clearAdminKey() {
  localStorage.removeItem('finagent_admin_key')
}

// ─── Fetch wrapper ────────────────────────────────────────────────────────────

async function adminFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const key = getAdminKey()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Admin-Key': key,
    ...(options.headers as Record<string, string> || {}),
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401 || res.status === 403) {
    clearAdminKey()
    if (typeof window !== 'undefined') window.location.href = '/admin/login'
    throw new Error('Sessão expirada. Faça login novamente.')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro desconhecido' }))
    throw new Error((err as { detail?: string }).detail || `HTTP ${res.status}`)
  }

  if (res.status === 204) return {} as T
  return res.json()
}

// ─── API methods ──────────────────────────────────────────────────────────────

export const adminApi = {
  // Dashboard stats
  stats: () => adminFetch<{
    active_clients: number
    active_agents: number
    imported_documents: number
    messages_today: number
    whatsapp_state: string | null
  }>('/api/admin/stats'),

  // Agents CRUD
  listAgents: () => adminFetch<{ agents: Array<Record<string, unknown>> }>('/api/admin/agents'),
  createAgent: (body: Record<string, unknown>) =>
    adminFetch<{ id: string; name: string }>('/api/admin/agents', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateAgent: (id: string, body: Record<string, unknown>) =>
    adminFetch<Record<string, unknown>>(`/api/admin/agents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deactivateAgent: (id: string) =>
    adminFetch<Record<string, unknown>>(`/api/admin/agents/${id}`, { method: 'DELETE' }),
  assignAgent: (agentId: string, tenantId: string) =>
    adminFetch<Record<string, unknown>>(`/api/admin/agents/${agentId}/assign/${tenantId}`, {
      method: 'POST',
    }),

  // Tenants
  listTenants: () =>
    adminFetch<{ tenants: Array<Record<string, unknown>>; total: number }>('/api/admin/tenants'),
  createTenant: (body: Record<string, unknown>) =>
    adminFetch<{ id: string; name: string }>('/api/admin/tenants', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // WhatsApp (Evolution API)
  whatsappStatus: () => adminFetch<Record<string, unknown>>('/api/admin/whatsapp/status'),
  whatsappConnect: () =>
    adminFetch<Record<string, unknown>>('/api/admin/whatsapp/connect', { method: 'POST' }),
  whatsappQRCode: () => adminFetch<Record<string, unknown>>('/api/admin/whatsapp/qrcode'),
  whatsappDisconnect: () =>
    adminFetch<Record<string, unknown>>('/api/admin/whatsapp/disconnect', { method: 'DELETE' }),
}
