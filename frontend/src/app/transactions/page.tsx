'use client'
import { useEffect, useState } from 'react'
import AppLayout from '@/components/layout/AppLayout'
import { transactions, ApiError } from '@/lib/api'
import { Plus, Search, Filter, Trash2, Edit2, Check, X, ChevronLeft, ChevronRight } from 'lucide-react'

interface Tx {
  id: string
  type: string
  amount: number
  description: string
  date: string
  status: string
  category_id: string | null
  notes: string | null
}

function fmt(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

const TYPE_COLORS: Record<string, string> = {
  income: 'bg-emerald-100 text-emerald-700',
  expense: 'bg-red-100 text-red-600',
  transfer: 'bg-blue-100 text-blue-600',
}
const STATUS_COLORS: Record<string, string> = {
  paid: 'bg-emerald-100 text-emerald-700',
  pending: 'bg-amber-100 text-amber-700',
  overdue: 'bg-red-100 text-red-600',
}
const TYPE_LABELS: Record<string, string> = { income: 'Receita', expense: 'Despesa', transfer: 'Transferência' }
const STATUS_LABELS: Record<string, string> = { paid: 'Pago', pending: 'Pendente', overdue: 'Atrasado' }

export default function TransactionsPage() {
  const [items, setItems] = useState<Tx[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ type: 'expense', amount: '', description: '', date: new Date().toISOString().split('T')[0], status: 'paid', notes: '' })
  const [saving, setSaving] = useState(false)
  const LIMIT = 20

  async function load(off = offset) {
    setLoading(true)
    setError('')
    try {
      const res = await transactions.list({ search, type: typeFilter || undefined, status: statusFilter || undefined, limit: LIMIT, offset: off })
      setItems(res.items as Tx[])
      setTotal(res.total)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Erro ao carregar')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0); setOffset(0) }, [search, typeFilter, statusFilter])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await transactions.create({ ...form, amount: parseFloat(form.amount) })
      setShowForm(false)
      setForm({ type: 'expense', amount: '', description: '', date: new Date().toISOString().split('T')[0], status: 'paid', notes: '' })
      load(0)
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Deletar esta transação?')) return
    try {
      await transactions.delete(id)
      load(offset)
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Erro ao deletar')
    }
  }

  return (
    <AppLayout>
      <div className="p-6 lg:p-8 max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Transações</h1>
            <p className="text-slate-500 text-sm mt-0.5">{total} transações encontradas</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 transition-all"
          >
            <Plus size={16} />
            Nova Transação
          </button>
        </div>

        {/* New transaction form */}
        {showForm && (
          <div className="bg-white rounded-2xl border border-slate-100 p-6 mb-6">
            <h2 className="font-semibold text-slate-800 mb-4">Nova Transação</h2>
            <form onSubmit={handleCreate} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Tipo</label>
                <select value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                  <option value="expense">Despesa</option>
                  <option value="income">Receita</option>
                  <option value="transfer">Transferência</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Valor (R$)</label>
                <input type="number" step="0.01" min="0.01" required
                  value={form.amount} onChange={e => setForm(p => ({ ...p, amount: e.target.value }))}
                  placeholder="0,00"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Data</label>
                <input type="date" required value={form.date}
                  onChange={e => setForm(p => ({ ...p, date: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1">Descrição</label>
                <input type="text" required value={form.description}
                  onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                  placeholder="Ex: Aluguel, Salário, Supermercado..."
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Status</label>
                <select value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                  <option value="paid">Pago</option>
                  <option value="pending">Pendente</option>
                </select>
              </div>
              <div className="sm:col-span-2 lg:col-span-3 flex gap-3 justify-end">
                <button type="button" onClick={() => setShowForm(false)}
                  className="px-4 py-2 text-sm border border-slate-200 rounded-xl text-slate-600 hover:bg-slate-50 transition-all">
                  Cancelar
                </button>
                <button type="submit" disabled={saving}
                  className="px-6 py-2 bg-blue-600 text-white text-sm rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-all">
                  {saving ? 'Salvando...' : 'Salvar Transação'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-slate-100 p-4 mb-4 flex flex-wrap gap-3">
          <div className="flex items-center gap-2 flex-1 min-w-48">
            <Search size={16} className="text-slate-400 flex-shrink-0" />
            <input
              type="text"
              placeholder="Buscar transações..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="flex-1 text-sm border-none outline-none bg-transparent text-slate-700 placeholder-slate-400"
            />
          </div>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">Todos os tipos</option>
            <option value="income">Receita</option>
            <option value="expense">Despesa</option>
            <option value="transfer">Transferência</option>
          </select>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">Todos os status</option>
            <option value="paid">Pago</option>
            <option value="pending">Pendente</option>
            <option value="overdue">Atrasado</option>
          </select>
        </div>

        {/* Table */}
        <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-slate-400 text-sm">Carregando...</div>
          ) : error ? (
            <div className="p-8 text-center text-red-500 text-sm">{error}</div>
          ) : items.length === 0 ? (
            <div className="p-12 text-center">
              <p className="text-slate-400 text-sm">Nenhuma transação encontrada.</p>
              <p className="text-slate-400 text-xs mt-1">Clique em "Nova Transação" ou importe um extrato no Chat.</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50">
                      <th className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Data</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Descrição</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Tipo</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Valor</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map(tx => (
                      <tr key={tx.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                        <td className="px-6 py-4 text-slate-500 whitespace-nowrap">
                          {new Date(tx.date + 'T12:00:00').toLocaleDateString('pt-BR')}
                        </td>
                        <td className="px-4 py-4">
                          <p className="font-medium text-slate-700">{tx.description}</p>
                          {tx.notes && <p className="text-xs text-slate-400 mt-0.5">{tx.notes}</p>}
                        </td>
                        <td className="px-4 py-4">
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TYPE_COLORS[tx.type] || 'bg-slate-100 text-slate-600'}`}>
                            {TYPE_LABELS[tx.type] || tx.type}
                          </span>
                        </td>
                        <td className={`px-4 py-4 text-right font-semibold ${tx.type === 'income' ? 'text-emerald-600' : 'text-slate-700'}`}>
                          {tx.type === 'income' ? '+' : tx.type === 'expense' ? '-' : ''}{fmt(tx.amount)}
                        </td>
                        <td className="px-4 py-4">
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[tx.status] || 'bg-slate-100 text-slate-600'}`}>
                            {STATUS_LABELS[tx.status] || tx.status}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <button onClick={() => handleDelete(tx.id)}
                            className="text-slate-300 hover:text-red-500 transition-colors p-1 rounded-lg hover:bg-red-50">
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {total > LIMIT && (
                <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100">
                  <p className="text-sm text-slate-500">
                    Mostrando {offset + 1}–{Math.min(offset + LIMIT, total)} de {total}
                  </p>
                  <div className="flex gap-2">
                    <button onClick={() => { const o = Math.max(0, offset - LIMIT); setOffset(o); load(o) }}
                      disabled={offset === 0}
                      className="p-2 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">
                      <ChevronLeft size={16} />
                    </button>
                    <button onClick={() => { const o = offset + LIMIT; setOffset(o); load(o) }}
                      disabled={offset + LIMIT >= total}
                      className="p-2 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">
                      <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AppLayout>
  )
}
