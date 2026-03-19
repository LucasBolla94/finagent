'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { adminApi, getAdminKey } from '@/lib/adminApi'
import {
  ChevronLeft, Users, Bot, Loader2, Search,
  ChevronRight, Building2, UserCheck
} from 'lucide-react'

type Tenant = {
  id: string
  name: string
  schema_name: string
  is_active: boolean
  created_at?: string
  agent_name?: string
  agent_id?: string
  user_count?: number
}

type Agent = {
  id: string
  name: string
  is_active: boolean
}

export default function TenantsPage() {
  const router = useRouter()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [message, setMessage] = useState('')
  const [assignModal, setAssignModal] = useState<Tenant | null>(null)
  const [selectedAgent, setSelectedAgent] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!getAdminKey()) { router.push('/admin'); return }
    loadAll()
  }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const [tenRes, agRes] = await Promise.all([
        adminApi.listTenants(),
        adminApi.listAgents(),
      ])
      setTenants((tenRes.tenants as Tenant[]) || [])
      setAgents(((agRes.agents as Agent[]) || []).filter(a => a.is_active))
    } catch (e) {
      setMessage(`❌ Erro ao carregar: ${e instanceof Error ? e.message : 'Tente novamente'}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleAssign() {
    if (!assignModal || !selectedAgent) return
    setSaving(true)
    try {
      await adminApi.assignAgent(selectedAgent, assignModal.id)
      const agentName = agents.find(a => a.id === selectedAgent)?.name
      setMessage(`✅ Agente "${agentName}" atribuído a "${assignModal.name}"!`)
      setAssignModal(null)
      setSelectedAgent('')
      await loadAll()
    } catch (e) {
      setMessage(`❌ ${e instanceof Error ? e.message : 'Erro na atribuição'}`)
    } finally {
      setSaving(false)
    }
  }

  const filtered = tenants.filter(t =>
    t.name?.toLowerCase().includes(search.toLowerCase()) ||
    t.schema_name?.toLowerCase().includes(search.toLowerCase())
  )

  function formatDate(d?: string) {
    if (!d) return '–'
    return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' })
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b border-slate-100 px-6 py-4">
        <Link href="/admin" className="flex items-center gap-2 text-slate-600 hover:text-slate-800 text-sm mb-1 w-fit">
          <ChevronLeft size={16} />Voltar
        </Link>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-slate-800">Clientes</h1>
          <span className="text-sm text-slate-500 bg-slate-100 px-3 py-1 rounded-full">
            {tenants.length} clientes
          </span>
        </div>
      </div>

      <div className="p-6 max-w-4xl mx-auto">
        {message && (
          <div className={`rounded-xl px-4 py-3 text-sm mb-4 ${message.startsWith('❌') ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-green-50 text-green-700 border border-green-200'}`}>
            {message}
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-white rounded-2xl border border-slate-100 p-4 text-center">
            <p className="text-2xl font-bold text-blue-600">{tenants.length}</p>
            <p className="text-xs text-slate-500 mt-1">Total Clientes</p>
          </div>
          <div className="bg-white rounded-2xl border border-slate-100 p-4 text-center">
            <p className="text-2xl font-bold text-emerald-600">{tenants.filter(t => t.is_active).length}</p>
            <p className="text-xs text-slate-500 mt-1">Ativos</p>
          </div>
          <div className="bg-white rounded-2xl border border-slate-100 p-4 text-center">
            <p className="text-2xl font-bold text-purple-600">{tenants.filter(t => t.agent_id).length}</p>
            <p className="text-xs text-slate-500 mt-1">Com Agente</p>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar cliente por nome ou schema..."
            className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
          />
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={32} className="animate-spin text-slate-300" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-100 p-12 text-center">
            <Users size={40} className="text-slate-200 mx-auto mb-3" />
            <p className="text-slate-500 font-medium">
              {search ? 'Nenhum cliente encontrado' : 'Nenhum cliente cadastrado'}
            </p>
            <p className="text-sm text-slate-400 mt-1">
              {search ? 'Tente outra busca' : 'Clientes aparecem aqui após o registro'}
            </p>
          </div>
        ) : (
          <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden">
            <div className="grid grid-cols-[1fr_140px_160px_80px] gap-4 px-5 py-3 bg-slate-50 border-b border-slate-100 text-xs font-medium text-slate-500 uppercase tracking-wide">
              <span>Cliente</span>
              <span>Criado em</span>
              <span>Agente</span>
              <span></span>
            </div>
            {filtered.map((tenant, i) => (
              <div
                key={tenant.id}
                className={`grid grid-cols-[1fr_140px_160px_80px] gap-4 px-5 py-4 items-center ${i < filtered.length - 1 ? 'border-b border-slate-100' : ''} hover:bg-slate-50 transition-colors`}
              >
                {/* Name + schema */}
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${tenant.is_active ? 'bg-blue-50' : 'bg-slate-100'}`}>
                      <Building2 size={14} className={tenant.is_active ? 'text-blue-600' : 'text-slate-400'} />
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-slate-800 text-sm truncate">{tenant.name || '–'}</p>
                      <p className="text-xs text-slate-400 font-mono truncate">{tenant.schema_name}</p>
                    </div>
                  </div>
                </div>

                {/* Date */}
                <span className="text-sm text-slate-500">{formatDate(tenant.created_at)}</span>

                {/* Agent */}
                <div>
                  {tenant.agent_name ? (
                    <div className="flex items-center gap-1.5 text-sm text-purple-600">
                      <Bot size={13} />
                      <span className="truncate">{tenant.agent_name}</span>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400 italic">Sem agente</span>
                  )}
                </div>

                {/* Action */}
                <button
                  onClick={() => { setAssignModal(tenant); setSelectedAgent(tenant.agent_id || '') }}
                  title="Atribuir agente"
                  className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
                >
                  <UserCheck size={14} />
                  <span>Atribuir</span>
                  <ChevronRight size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Info box */}
        <div className="bg-blue-50 rounded-2xl p-5 mt-6 border border-blue-100">
          <p className="text-sm font-semibold text-blue-800 mb-1">ℹ️ Sobre Clientes</p>
          <p className="text-sm text-blue-700">
            Os clientes são criados automaticamente quando um usuário se registra pelo app.
            Cada cliente tem um schema isolado no banco de dados com suas transações, contas e documentos.
            Para que o chat funcione, atribua um agente ativo ao cliente.
          </p>
        </div>
      </div>

      {/* Assign Modal */}
      {assignModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-800">Atribuir Agente</h3>
              <button onClick={() => setAssignModal(null)} className="text-slate-400 hover:text-slate-600">
                ×
              </button>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              Cliente: <span className="font-medium text-slate-800">{assignModal.name}</span>
            </p>
            {agents.length === 0 ? (
              <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700 mb-4">
                Nenhum agente ativo disponível.{' '}
                <Link href="/admin/agents" className="underline font-medium">Criar um agente</Link>
              </div>
            ) : (
              <div className="mb-4">
                <label className="block text-xs font-medium text-slate-600 mb-1">Selecionar Agente</label>
                <select
                  value={selectedAgent}
                  onChange={e => setSelectedAgent(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 bg-white"
                >
                  <option value="">Escolha um agente...</option>
                  {agents.map(a => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="flex gap-3">
              <button
                onClick={handleAssign}
                disabled={!selectedAgent || saving || agents.length === 0}
                className="flex-1 flex items-center justify-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm transition-all"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <UserCheck size={16} />}
                Confirmar
              </button>
              <button onClick={() => setAssignModal(null)} className="px-4 py-2.5 rounded-xl text-sm text-slate-600 hover:bg-slate-100">
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
