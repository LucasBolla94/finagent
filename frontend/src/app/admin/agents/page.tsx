'use client'
import { useState, useEffect } from 'react'
import { adminApi } from '@/lib/adminApi'
import {
  Bot, Plus, Pencil, Trash2, UserPlus, RotateCcw,
  Loader2, CheckCircle2, X, ChevronDown, ChevronUp
} from 'lucide-react'

type Agent = {
  id: string
  name: string
  description?: string
  system_prompt?: string
  model?: string
  is_active: boolean
  tenant_name?: string
  tenant_id?: string
  client_count?: number
}

type Tenant = {
  id: string
  name: string
  email?: string
}

const MODELS = [
  { value: 'anthropic/claude-haiku-4', label: 'Claude Haiku 4 (rápido)' },
  { value: 'anthropic/claude-sonnet-4-5', label: 'Claude Sonnet 4.5 (padrão)' },
  { value: 'anthropic/claude-opus-4', label: 'Claude Opus 4 (poderoso)' },
  { value: 'google/gemini-flash-1.5', label: 'Gemini Flash 1.5 (econômico)' },
  { value: 'openai/gpt-4o-mini', label: 'GPT-4o Mini' },
]

const DEFAULT_PROMPT = `Você é o FinAgent, um assistente financeiro pessoal inteligente e empático.
Você ajuda o usuário a entender suas finanças, controlar gastos, identificar padrões e tomar melhores decisões financeiras.
Sempre responda em português brasileiro, de forma clara, objetiva e amigável.
Quando apresentar valores monetários, use o formato R$ X.XXX,XX.`

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editAgent, setEditAgent] = useState<Agent | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [assignModal, setAssignModal] = useState<Agent | null>(null)
  const [selectedTenant, setSelectedTenant] = useState('')

  const [form, setForm] = useState({
    name: '',
    description: '',
    system_prompt: DEFAULT_PROMPT,
    model: 'anthropic/claude-haiku-4',
  })

  useEffect(() => { loadAll() }, [])

  function flash(type: 'ok' | 'err', text: string) {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

  async function loadAll() {
    setLoading(true)
    try {
      const [agRes, tenRes] = await Promise.all([
        adminApi.listAgents(),
        adminApi.listTenants(),
      ])
      setAgents((agRes.agents as Agent[]) || [])
      setTenants((tenRes.tenants as Tenant[]) || [])
    } catch (e) {
      flash('err', `Erro ao carregar: ${e instanceof Error ? e.message : 'Tente novamente'}`)
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setEditAgent(null)
    setForm({ name: '', description: '', system_prompt: DEFAULT_PROMPT, model: 'anthropic/claude-haiku-4' })
    setShowForm(true)
    setExpandedId(null)
  }

  function openEdit(agent: Agent) {
    setEditAgent(agent)
    setForm({
      name: agent.name,
      description: agent.description || '',
      system_prompt: agent.system_prompt || DEFAULT_PROMPT,
      model: agent.model || 'anthropic/claude-haiku-4',
    })
    setShowForm(true)
    setExpandedId(null)
  }

  async function handleSave() {
    if (!form.name.trim()) { flash('err', 'Nome é obrigatório'); return }
    setSaving(true)
    try {
      if (editAgent) {
        await adminApi.updateAgent(editAgent.id, form)
        flash('ok', `Agente "${form.name}" atualizado!`)
      } else {
        await adminApi.createAgent(form)
        flash('ok', `Agente "${form.name}" criado!`)
      }
      setShowForm(false)
      await loadAll()
    } catch (e) {
      flash('err', e instanceof Error ? e.message : 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  async function handleToggleActive(agent: Agent) {
    const action = agent.is_active ? 'Desativar' : 'Reativar'
    if (!confirm(`${action} o agente "${agent.name}"?`)) return
    try {
      if (agent.is_active) {
        await adminApi.deactivateAgent(agent.id)
        flash('ok', `Agente "${agent.name}" desativado.`)
      } else {
        await adminApi.updateAgent(agent.id, { is_active: true })
        flash('ok', `Agente "${agent.name}" reativado!`)
      }
      await loadAll()
    } catch (e) {
      flash('err', e instanceof Error ? e.message : 'Erro')
    }
  }

  async function handleAssign() {
    if (!assignModal || !selectedTenant) return
    setSaving(true)
    try {
      await adminApi.assignAgent(assignModal.id, selectedTenant)
      const tenant = tenants.find(t => t.id === selectedTenant)
      flash('ok', `Agente "${assignModal.name}" atribuído a "${tenant?.name}"!`)
      setAssignModal(null)
      setSelectedTenant('')
      await loadAll()
    } catch (e) {
      flash('err', e instanceof Error ? e.message : 'Erro na atribuição')
    } finally {
      setSaving(false)
    }
  }

  const activeAgents = agents.filter(a => a.is_active)
  const inactiveAgents = agents.filter(a => !a.is_active)

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Agentes</h1>
          <p className="text-slate-500 text-sm mt-0.5">{activeAgents.length} ativo(s) · {inactiveAgents.length} inativo(s)</p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white font-medium px-4 py-2 rounded-xl text-sm transition-all shadow-sm"
        >
          <Plus size={16} /> Novo Agente
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

      {/* Create/Edit Form */}
      {showForm && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 mb-6 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <h2 className="font-semibold text-slate-800">{editAgent ? 'Editar Agente' : 'Criar Novo Agente'}</h2>
            <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600">
              <X size={18} />
            </button>
          </div>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1.5">Nome do Agente *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Ex: FinAgent"
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1.5">Modelo de IA</label>
                <select
                  value={form.model}
                  onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 bg-white"
                >
                  {MODELS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">Descrição</label>
              <input
                type="text"
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Breve descrição do agente"
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">
                System Prompt
                <span className="text-slate-400 font-normal ml-1">(define a personalidade e comportamento)</span>
              </label>
              <textarea
                value={form.system_prompt}
                onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                rows={7}
                className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 font-mono resize-y leading-relaxed"
              />
              <p className="text-xs text-slate-400 mt-1">{form.system_prompt.length} caracteres</p>
            </div>

            <div className="flex gap-3 pt-1">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium px-5 py-2.5 rounded-xl text-sm transition-all"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                {saving ? 'Salvando...' : editAgent ? 'Salvar Alterações' : 'Criar Agente'}
              </button>
              <button onClick={() => setShowForm(false)} className="px-5 py-2.5 rounded-xl text-sm text-slate-600 hover:bg-slate-100 transition-all">
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Agents List */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={32} className="animate-spin text-slate-300" />
        </div>
      ) : agents.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-100 p-12 text-center">
          <Bot size={40} className="text-slate-200 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">Nenhum agente criado</p>
          <p className="text-sm text-slate-400 mt-1">Crie o primeiro agente para começar</p>
          <button onClick={openCreate} className="mt-4 text-sm text-purple-600 font-medium hover:underline">
            + Criar agente
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {agents.map(agent => (
            <div key={agent.id} className={`bg-white rounded-2xl border overflow-hidden transition-all ${agent.is_active ? 'border-slate-100' : 'border-slate-200 opacity-70'}`}>
              <div className="p-5 flex items-center gap-4">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${agent.is_active ? 'bg-purple-50' : 'bg-slate-100'}`}>
                  <Bot size={20} className={agent.is_active ? 'text-purple-600' : 'text-slate-400'} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold text-slate-800 truncate">{agent.name}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${agent.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-500'}`}>
                      {agent.is_active ? 'Ativo' : 'Inativo'}
                    </span>
                  </div>
                  {agent.description && (
                    <p className="text-sm text-slate-500 mt-0.5 truncate">{agent.description}</p>
                  )}
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    <span className="text-xs text-slate-400">
                      {MODELS.find(m => m.value === agent.model)?.label || agent.model || 'Modelo padrão'}
                    </span>
                    {agent.tenant_name && (
                      <span className="text-xs text-blue-500">
                        👤 {agent.tenant_name}
                        {agent.client_count && agent.client_count > 1 ? ` +${agent.client_count - 1}` : ''}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={() => { setAssignModal(agent); setSelectedTenant('') }}
                    title="Atribuir a cliente"
                    className="p-2 text-blue-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                  >
                    <UserPlus size={16} />
                  </button>
                  {agent.is_active && (
                    <button
                      onClick={() => openEdit(agent)}
                      title="Editar"
                      className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all"
                    >
                      <Pencil size={16} />
                    </button>
                  )}
                  <button
                    onClick={() => handleToggleActive(agent)}
                    title={agent.is_active ? 'Desativar' : 'Reativar'}
                    className={`p-2 rounded-lg transition-all ${
                      agent.is_active
                        ? 'text-red-400 hover:text-red-600 hover:bg-red-50'
                        : 'text-emerald-500 hover:text-emerald-700 hover:bg-emerald-50'
                    }`}
                  >
                    {agent.is_active ? <Trash2 size={16} /> : <RotateCcw size={16} />}
                  </button>
                  <button
                    onClick={() => setExpandedId(expandedId === agent.id ? null : agent.id)}
                    className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all"
                  >
                    {expandedId === agent.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>
              </div>

              {expandedId === agent.id && (
                <div className="border-t border-slate-100 px-5 py-4 bg-slate-50">
                  <p className="text-xs font-medium text-slate-500 mb-2 uppercase tracking-wide">System Prompt</p>
                  <pre className="text-xs text-slate-600 whitespace-pre-wrap font-mono leading-relaxed max-h-48 overflow-y-auto">
                    {agent.system_prompt || '(sem system prompt definido)'}
                  </pre>
                </div>
              )}
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
              Agente: <span className="font-medium text-slate-800">{assignModal.name}</span>
            </p>
            {tenants.length === 0 ? (
              <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700 mb-4">
                Nenhum cliente cadastrado ainda.
              </div>
            ) : (
              <div className="mb-4">
                <label className="block text-xs font-medium text-slate-600 mb-1.5">Selecionar Cliente</label>
                <select
                  value={selectedTenant}
                  onChange={e => setSelectedTenant(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 bg-white"
                >
                  <option value="">Escolha um cliente...</option>
                  {tenants.map(t => (
                    <option key={t.id} value={t.id}>{t.name} {t.email ? `(${t.email})` : ''}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="flex gap-3">
              <button
                onClick={handleAssign}
                disabled={!selectedTenant || saving}
                className="flex-1 flex items-center justify-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
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
