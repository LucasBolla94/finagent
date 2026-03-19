'use client'
import { useState, useEffect } from 'react'
import { adminApi } from '@/lib/adminApi'
import {
  Users, Bot, Loader2, Search, Building2,
  UserCheck, Plus, X, Phone, Mail, CheckCircle2
} from 'lucide-react'

type Tenant = {
  id: string
  name: string
  email?: string
  business_name?: string
  whatsapp_number?: string
  telegram_chat_id?: string
  plan?: string
  is_active: boolean
  created_at?: string
  agent_name?: string
  agent_id?: string
}

type Agent = {
  id: string
  name: string
  is_active: boolean
}

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [assignModal, setAssignModal] = useState<Tenant | null>(null)
  const [selectedAgent, setSelectedAgent] = useState('')
  const [saving, setSaving] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ name: '', email: '', whatsapp_number: '' })

  useEffect(() => { loadAll() }, [])

  function flash(type: 'ok' | 'err', text: string) {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

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
      flash('err', `Erro ao carregar: ${e instanceof Error ? e.message : 'Tente novamente'}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleCreateTenant() {
    if (!createForm.name.trim()) { flash('err', 'Nome é obrigatório'); return }
    setSaving(true)
    try {
      await adminApi.createTenant(createForm)
      flash('ok', `Cliente "${createForm.name}" criado!`)
      setShowCreate(false)
      setCreateForm({ name: '', email: '', whatsapp_number: '' })
      await loadAll()
    } catch (e) {
      flash('err', e instanceof Error ? e.message : 'Erro ao criar cliente')
    } finally {
      setSaving(false)
    }
  }

  async function handleAssign() {
    if (!assignModal || !selectedAgent) return
    setSaving(true)
    try {
      await adminApi.assignAgent(selectedAgent, assignModal.id)
      const agentName = agents.find(a => a.id === selectedAgent)?.name
      flash('ok', `Agente "${agentName}" atribuído a "${assignModal.name}"!`)
      setAssignModal(null)
      setSelectedAgent('')
      await loadAll()
    } catch (e) {
      flash('err', e instanceof Error ? e.message : 'Erro na atribuição')
    } finally {
      setSaving(false)
    }
  }

  const filtered = tenants.filter(t =>
    t.name?.toLowerCase().includes(search.toLowerCase()) ||
    t.email?.toLowerCase().includes(search.toLowerCase()) ||
    t.whatsapp_number?.includes(search)
  )

  function formatDate(d?: string) {
    if (!d) return '–'
    return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' })
  }

  function formatPhone(p?: string) {
    if (!p) return p
    const clean = p.replace(/\D/g, '')
    if (clean.length >= 12) {
      return `+${clean.slice(0, 2)} ${clean.slice(2, 4)} ${clean.slice(4, 9)}-${clean.slice(9)}`
    }
    return p
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Clientes</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {tenants.filter(t => t.is_active).length} ativo(s) · {tenants.filter(t => !t.is_active).length} inativo(s)
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium px-4 py-2 rounded-xl text-sm transition-all shadow-sm"
        >
          <Plus size={16} /> Novo Cliente
        </button>
      </div>

      {/* Flash message */}
      {message && (
        <div className={`rounded-xl px-4 py-3 text-sm mb-4 flex items-center justify-between ${
          message.type === 'err'
            ? 'bg-red-50 text-red-700 border border-red-200'
            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        }`}>
          <span>{message.text}</span>
          <button onClick={() => setMessage(null)}><X size={14} /></button>
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 mb-6 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <h2 className="font-semibold text-slate-800">Novo Cliente</h2>
            <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-600">
              <X size={18} />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">Nome *</label>
              <input
                type="text"
                value={createForm.name}
                onChange={e => setCreateForm(f => ({ ...f, name: e.target.value }))}
                placeholder="Nome completo"
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">Email</label>
              <input
                type="email"
                value={createForm.email}
                onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))}
                placeholder="email@exemplo.com"
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">WhatsApp</label>
              <input
                type="text"
                value={createForm.whatsapp_number}
                onChange={e => setCreateForm(f => ({ ...f, whatsapp_number: e.target.value }))}
                placeholder="5511999999999"
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleCreateTenant}
              disabled={saving}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium px-5 py-2.5 rounded-xl text-sm"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
              {saving ? 'Criando...' : 'Criar Cliente'}
            </button>
            <button onClick={() => setShowCreate(false)} className="px-5 py-2.5 rounded-xl text-sm text-slate-600 hover:bg-slate-100">
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Stats */}
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
          placeholder="Buscar por nome, email ou WhatsApp..."
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
          {!search && (
            <button onClick={() => setShowCreate(true)} className="mt-4 text-sm text-blue-600 font-medium hover:underline">
              + Criar cliente manualmente
            </button>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden">
          <div className="grid grid-cols-[1fr_180px_160px_80px] gap-4 px-5 py-3 bg-slate-50 border-b border-slate-100 text-xs font-medium text-slate-500 uppercase tracking-wide">
            <span>Cliente</span>
            <span>Contato</span>
            <span>Agente</span>
            <span></span>
          </div>
          {filtered.map((tenant, i) => (
            <div
              key={tenant.id}
              className={`grid grid-cols-[1fr_180px_160px_80px] gap-4 px-5 py-4 items-center ${
                i < filtered.length - 1 ? 'border-b border-slate-100' : ''
              } hover:bg-slate-50 transition-colors`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${tenant.is_active ? 'bg-blue-50' : 'bg-slate-100'}`}>
                  <Building2 size={14} className={tenant.is_active ? 'text-blue-600' : 'text-slate-400'} />
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-slate-800 text-sm truncate">{tenant.name || '–'}</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`text-xs px-1.5 py-0.5 rounded-full ${tenant.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-500'}`}>
                      {tenant.is_active ? 'Ativo' : 'Inativo'}
                    </span>
                    <span className="text-xs text-slate-400">{formatDate(tenant.created_at)}</span>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-1 min-w-0">
                {tenant.email && (
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <Mail size={11} className="text-slate-400 flex-shrink-0" />
                    <span className="truncate">{tenant.email}</span>
                  </div>
                )}
                {tenant.whatsapp_number && (
                  <div className="flex items-center gap-1.5 text-xs text-emerald-600">
                    <Phone size={11} className="flex-shrink-0" />
                    <span className="truncate">{formatPhone(tenant.whatsapp_number)}</span>
                  </div>
                )}
                {!tenant.email && !tenant.whatsapp_number && (
                  <span className="text-xs text-slate-400 italic">sem contato</span>
                )}
              </div>

              <div>
                {tenant.agent_name ? (
                  <div className="flex items-center gap-1.5 text-sm text-purple-600">
                    <Bot size={13} />
                    <span className="truncate">{tenant.agent_name}</span>
                  </div>
                ) : (
                  <span className="text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">Sem agente</span>
                )}
              </div>

              <button
                onClick={() => { setAssignModal(tenant); setSelectedAgent(tenant.agent_id || '') }}
                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors whitespace-nowrap"
              >
                <UserCheck size={14} />
                Atribuir
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Assign Modal */}
      {assignModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-800">Atribuir Agente</h3>
              <button onClick={() => setAssignModal(null)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              Cliente: <span className="font-medium text-slate-800">{assignModal.name}</span>
            </p>
            {agents.length === 0 ? (
              <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700 mb-4">
                Nenhum agente ativo. Crie um agente primeiro em Agentes.
              </div>
            ) : (
              <div className="mb-4">
                <label className="block text-xs font-medium text-slate-600 mb-1.5">Selecionar Agente</label>
                <select
                  value={selectedAgent}
                  onChange={e => setSelectedAgent(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 bg-white"
                >
                  <option value="">Escolha um agente...</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
            )}
            <div className="flex gap-3">
              <button
                onClick={handleAssign}
                disabled={!selectedAgent || saving || agents.length === 0}
                className="flex-1 flex items-center justify-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm"
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
