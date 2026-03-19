'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { adminApi, getAdminKey } from '@/lib/adminApi'
import {
  ChevronLeft, Bot, Plus, Pencil, Trash2, UserPlus,
  Loader2, CheckCircle2, X, ChevronDown, ChevronUp
} from 'lucide-react'

type Agent = {
  id: string
  name: string
  description?: string
  system_prompt?: string
  model?: string
  is_active: boolean
  tenant_id?: string
}

type Tenant = {
  id: string
  name: string
  schema_name: string
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
  const router = useRouter()
  const [agents, setAgents] = useState<Agent[]>([])
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editAgent, setEditAgent] = useState<Agent | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [assignModal, setAssignModal] = useState<{ agentId: string; agentName: string } | null>(null)
  const [selectedTenant, setSelectedTenant] = useState('')

  const [form, setForm] = useState({
    name: '',
    description: '',
    system_prompt: DEFAULT_PROMPT,
    model: 'anthropic/claude-haiku-4',
  })

  useEffect(() => {
    if (!getAdminKey()) { router.push('/admin'); return }
    loadAll()
  }, [])

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
      setMessage(`❌ Erro ao carregar: ${e instanceof Error ? e.message : 'Tente novamente'}`)
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setEditAgent(null)
    setForm({ name: '', description: '', system_prompt: DEFAULT_PROMPT, model: 'anthropic/claude-haiku-4' })
    setShowForm(true)
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
  }

  async function handleSave() {
    if (!form.name.trim()) { setMessage('❌ Nome é obrigatório'); return }
    setSaving(true)
    setMessage('')
    try {
      if (editAgent) {
        await adminApi.updateAgent(editAgent.id, form)
        setMessage('✅ Agente atualizado!')
      } else {
        await adminApi.createAgent(form)
        setMessage('✅ Agente criado!')
      }
      setShowForm(false)
      await loadAll()
    } catch (e) {
      setMessage(`❌ ${e instanceof Error ? e.message : 'Erro ao salvar'}`)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeactivate(agent: Agent) {
    if (!confirm(`Desativar o agente "${agent.name}"? Ele não responderá mais.`)) return
    try {
      await adminApi.deactivateAgent(agent.id)
      setMessage('✅ Agente desativado.')
      await loadAll()
    } catch (e) {
      setMessage(`❌ ${e instanceof Error ? e.message : 'Erro'}`)
    }
  }

  async function handleAssign() {
    if (!assignModal || !selectedTenant) return
    setSaving(true)
    try {
      await adminApi.assignAgent(assignModal.agentId, selectedTenant)
      setMessage(`✅ Agente "${assignModal.agentName}" atribuído ao cliente!`)
      setAssignModal(null)
      setSelectedTenant('')
      await loadAll()
    } catch (e) {
      setMessage(`❌ ${e instanceof Error ? e.message : 'Erro na atribuição'}`)
    } finally {
      setSaving(false)
    }
  }

  const tenantMap = Object.fromEntries(tenants.map(t => [t.id, t]))

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b border-slate-100 px-6 py-4">
        <Link href="/admin" className="flex items-center gap-2 text-slate-600 hover:text-slate-800 text-sm mb-1 w-fit">
          <ChevronLeft size={16} />Voltar
        </Link>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-slate-800">Gerenciar Agentes</h1>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white font-medium px-4 py-2 rounded-xl text-sm transition-all"
          >
            <Plus size={16} />Novo Agente
          </button>
        </div>
      </div>

      <div className="p-6 max-w-3xl mx-auto">
        {message && (
          <div className={`rounded-xl px-4 py-3 text-sm mb-4 ${message.startsWith('❌') ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-green-50 text-green-700 border border-green-200'}`}>
            {message}
          </div>
        )}

        {/* Create/Edit Form */}
        {showForm && (
          <div className="bg-white rounded-2xl border border-slate-100 p-6 mb-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-800">{editAgent ? 'Editar Agente' : 'Criar Novo Agente'}</h2>
              <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Nome do Agente *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Ex: FinAgent Principal"
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Descrição</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="Breve descrição do agente"
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Modelo de IA</label>
                <select
                  value={form.model}
                  onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 bg-white"
                >
                  {MODELS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">System Prompt</label>
                <textarea
                  value={form.system_prompt}
                  onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                  rows={6}
                  className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 font-mono resize-y"
                />
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
                <button
                  onClick={() => setShowForm(false)}
                  className="px-5 py-2.5 rounded-xl text-sm text-slate-600 hover:bg-slate-100 transition-all"
                >
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
          </div>
        ) : (
          <div className="space-y-3">
            {agents.map(agent => (
              <div key={agent.id} className="bg-white rounded-2xl border border-slate-100 overflow-hidden">
                <div className="p-5 flex items-center gap-4">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${agent.is_active ? 'bg-purple-50' : 'bg-slate-100'}`}>
                    <Bot size={20} className={agent.is_active ? 'text-purple-600' : 'text-slate-400'} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-slate-800 truncate">{agent.name}</p>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${agent.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-500'}`}>
                        {agent.is_active ? 'Ativo' : 'Inativo'}
                      </span>
                    </div>
                    {agent.description && (
                      <p className="text-sm text-slate-500 mt-0.5 truncate">{agent.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs text-slate-400">{MODELS.find(m => m.value === agent.model)?.label || agent.model || 'Modelo padrão'}</span>
                      {agent.tenant_id && tenantMap[agent.tenant_id] && (
                        <span className="text-xs text-blue-500">👤 {tenantMap[agent.tenant_id].name}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => setAssignModal({ agentId: agent.id, agentName: agent.name })}
                      title="Atribuir a cliente"
                      className="p-2 text-blue-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                    >
                      <UserPlus size={16} />
                    </button>
                    <button
                      onClick={() => openEdit(agent)}
                      title="Editar"
                      className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all"
                    >
                      <Pencil size={16} />
                    </button>
                    {agent.is_active && (
                      <button
                        onClick={() => handleDeactivate(agent)}
                        title="Desativar"
                        className="p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                    <button
                      onClick={() => setExpandedId(expandedId === agent.id ? null : agent.id)}
                      className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-all"
                    >
                      {expandedId === agent.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                  </div>
                </div>

                {expandedId === agent.id && agent.system_prompt && (
                  <div className="border-t border-slate-100 px-5 py-4 bg-slate-50">
                    <p className="text-xs font-medium text-slate-500 mb-2">System Prompt:</p>
                    <pre className="text-xs text-slate-600 whitespace-pre-wrap font-mono leading-relaxed">{agent.system_prompt}</pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Assign Modal */}
      {assignModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-800">Atribuir Agente a Cliente</h3>
              <button onClick={() => setAssignModal(null)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              Agente: <span className="font-medium text-slate-800">{assignModal.agentName}</span>
            </p>
            <div className="mb-4">
              <label className="block text-xs font-medium text-slate-600 mb-1">Selecionar Cliente</label>
              <select
                value={selectedTenant}
                onChange={e => setSelectedTenant(e.target.value)}
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
              >
                <option value="">Escolha um cliente...</option>
                {tenants.map(t => (
                  <option key={t.id} value={t.id}>{t.name} ({t.schema_name})</option>
                ))}
              </select>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleAssign}
                disabled={!selectedTenant || saving}
                className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl text-sm transition-all"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
                Atribuir
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
