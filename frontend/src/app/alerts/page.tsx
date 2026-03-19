'use client'
import { useEffect, useState } from 'react'
import AppLayout from '@/components/layout/AppLayout'
import { alerts as alertsApi, ApiError } from '@/lib/api'
import { Plus, Bell, Trash2, ToggleLeft, ToggleRight, AlertCircle } from 'lucide-react'

interface Alert {
  id: string
  type: string
  name: string
  condition: Record<string, unknown>
  message: string
  channels: string[]
  is_active: boolean
  trigger_count: number
  last_triggered: string | null
}

const TYPE_LABELS: Record<string, string> = {
  balance_below: '💰 Saldo Abaixo de',
  expense_above: '📈 Despesas Acima de',
  bill_due: '📅 Conta a Vencer',
  category_limit: '🏷️ Limite por Categoria',
}
const TYPE_DESCRIPTIONS: Record<string, string> = {
  balance_below: 'Avisa quando o saldo cair abaixo de um valor',
  expense_above: 'Avisa quando as despesas mensais ultrapassarem um valor',
  bill_due: 'Avisa quando uma conta está prestes a vencer',
  category_limit: 'Avisa quando uma categoria ultrapassar o orçamento',
}

export default function AlertsPage() {
  const [items, setItems] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ type: 'balance_below', name: '', threshold: '', days: '3', message: '', channels: ['whatsapp'] })
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const res = await alertsApi.list()
      setItems((res as { alerts: Alert[] }).alerts || [])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  function getCondition() {
    if (form.type === 'bill_due') return { days: parseInt(form.days) }
    return { threshold: parseFloat(form.threshold) }
  }

  function getDefaultMessage() {
    if (form.type === 'balance_below') return `⚠️ Atenção! Seu saldo está abaixo de R$ ${form.threshold}.`
    if (form.type === 'expense_above') return `📊 Suas despesas do mês ultrapassaram R$ ${form.threshold}.`
    if (form.type === 'bill_due') return `📅 Você tem uma conta vencendo em ${form.days} dias!`
    return `🚨 Alerta: ${form.name}`
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await alertsApi.create({
        type: form.type,
        name: form.name,
        condition: getCondition(),
        message: form.message || getDefaultMessage(),
        channels: form.channels,
      })
      setShowForm(false)
      setForm({ type: 'balance_below', name: '', threshold: '', days: '3', message: '', channels: ['whatsapp'] })
      load()
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Erro ao criar alerta')
    } finally { setSaving(false) }
  }

  async function toggleAlert(id: string, current: boolean) {
    try {
      await alertsApi.update(id, { is_active: !current })
      load()
    } catch (e) { console.error(e) }
  }

  async function deleteAlert(id: string) {
    if (!confirm('Deletar este alerta?')) return
    try {
      await alertsApi.delete(id)
      load()
    } catch (e) { console.error(e) }
  }

  return (
    <AppLayout>
      <div className="p-6 lg:p-8 max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Alertas</h1>
            <p className="text-slate-500 text-sm mt-0.5">Notificações automáticas via WhatsApp/Telegram</p>
          </div>
          <button onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 transition-all">
            <Plus size={16} /> Novo Alerta
          </button>
        </div>

        {showForm && (
          <div className="bg-white rounded-2xl border border-slate-100 p-6 mb-6">
            <h2 className="font-semibold text-slate-800 mb-4">Criar Novo Alerta</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Tipo de alerta</label>
                  <select value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                    {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <p className="text-xs text-slate-400 mt-1">{TYPE_DESCRIPTIONS[form.type]}</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Nome do alerta</label>
                  <input type="text" required value={form.name}
                    onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="Ex: Saldo baixo Nubank"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                </div>
              </div>

              {form.type === 'bill_due' ? (
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Avisar com quantos dias de antecedência?</label>
                  <input type="number" min="1" max="30" value={form.days}
                    onChange={e => setForm(p => ({ ...p, days: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Valor limite (R$) — {form.type === 'balance_below' ? 'abaixo de' : 'acima de'}
                  </label>
                  <input type="number" step="0.01" min="0" required value={form.threshold}
                    onChange={e => setForm(p => ({ ...p, threshold: e.target.value }))}
                    placeholder="500,00"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Mensagem (deixe em branco para usar padrão)</label>
                <input type="text" value={form.message}
                  onChange={e => setForm(p => ({ ...p, message: e.target.value }))}
                  placeholder={getDefaultMessage()}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>

              <div className="flex gap-3 justify-end">
                <button type="button" onClick={() => setShowForm(false)}
                  className="px-4 py-2 text-sm border border-slate-200 rounded-xl text-slate-600 hover:bg-slate-50">Cancelar</button>
                <button type="submit" disabled={saving}
                  className="px-6 py-2 bg-blue-600 text-white text-sm rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50">
                  {saving ? 'Criando...' : 'Criar Alerta'}
                </button>
              </div>
            </form>
          </div>
        )}

        {loading ? (
          <div className="text-center py-12 text-slate-400 text-sm">Carregando...</div>
        ) : items.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-100 p-12 text-center">
            <Bell size={32} className="mx-auto text-slate-300 mb-3" />
            <p className="text-slate-500 font-medium">Nenhum alerta configurado</p>
            <p className="text-slate-400 text-sm mt-1">Crie alertas para receber notificações automáticas no WhatsApp</p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map(alert => (
              <div key={alert.id} className={`bg-white rounded-2xl border transition-all ${alert.is_active ? 'border-slate-100' : 'border-slate-100 opacity-60'}`}>
                <div className="flex items-center gap-4 p-5">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${alert.is_active ? 'bg-blue-50' : 'bg-slate-100'}`}>
                    <Bell size={18} className={alert.is_active ? 'text-blue-600' : 'text-slate-400'} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-slate-800">{alert.name}</p>
                      <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
                        {TYPE_LABELS[alert.type] || alert.type}
                      </span>
                    </div>
                    <p className="text-sm text-slate-500 mt-0.5 truncate">{alert.message}</p>
                    {alert.trigger_count > 0 && (
                      <p className="text-xs text-slate-400 mt-1">
                        Disparado {alert.trigger_count}x
                        {alert.last_triggered && ` — último: ${new Date(alert.last_triggered).toLocaleDateString('pt-BR')}`}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div className="flex gap-1 text-xs text-slate-400">
                      {alert.channels.includes('whatsapp') && <span className="bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded-full">WA</span>}
                      {alert.channels.includes('telegram') && <span className="bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">TG</span>}
                    </div>
                    <button onClick={() => toggleAlert(alert.id, alert.is_active)}
                      className={`transition-colors ${alert.is_active ? 'text-blue-500' : 'text-slate-300'}`}>
                      {alert.is_active ? <ToggleRight size={28} /> : <ToggleLeft size={28} />}
                    </button>
                    <button onClick={() => deleteAlert(alert.id)}
                      className="text-slate-300 hover:text-red-500 transition-colors p-1">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
