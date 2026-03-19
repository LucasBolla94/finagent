'use client'
import { useEffect, useState } from 'react'
import AppLayout from '@/components/layout/AppLayout'
import { reports, accounts, ApiError } from '@/lib/api'
import { TrendingUp, TrendingDown, Wallet, AlertCircle, RefreshCw } from 'lucide-react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from 'recharts'

interface Summary {
  income: number
  expenses: number
  net: number
  pending_income: number
  pending_expenses: number
  transaction_count: { paid: number; pending: number }
  top_expense_categories: Array<{ category: string; total: number; count: number; percentage: number }>
}

interface CashFlowItem {
  month: string
  income: number
  expenses: number
  net: number
}

function fmt(v: number) {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function formatMonth(dateStr: string) {
  const d = new Date(dateStr + 'T12:00:00')
  return d.toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [cashFlow, setCashFlow] = useState<CashFlowItem[]>([])
  const [totalBalance, setTotalBalance] = useState<number>(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [sum, cf, accts] = await Promise.all([
        reports.summary(),
        reports.cashFlow(6),
        accounts.list(),
      ])
      setSummary(sum as Summary)
      setCashFlow((cf.cash_flow as CashFlowItem[]) || [])
      setTotalBalance((accts as { total_balance: number }).total_balance || 0)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Erro ao carregar dados')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const chartData = cashFlow.map(item => ({
    ...item,
    name: formatMonth(item.month as string),
  }))

  return (
    <AppLayout>
      <div className="p-6 lg:p-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Dashboard</h1>
            <p className="text-slate-500 text-sm mt-0.5">
              {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
            </p>
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-sm text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-100 transition-all disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            Atualizar
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-6 text-sm">
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {loading && !summary ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-white rounded-2xl p-6 border border-slate-100 animate-pulse">
                <div className="h-3 bg-slate-200 rounded w-1/2 mb-4" />
                <div className="h-8 bg-slate-200 rounded w-3/4" />
              </div>
            ))}
          </div>
        ) : summary ? (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <div className="bg-white rounded-2xl p-6 border border-slate-100 card-hover">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm text-slate-500 font-medium">Saldo Total</p>
                  <div className="w-9 h-9 bg-blue-50 rounded-xl flex items-center justify-center">
                    <Wallet size={18} className="text-blue-600" />
                  </div>
                </div>
                <p className="text-2xl font-bold text-slate-800">{fmt(totalBalance)}</p>
                <p className="text-xs text-slate-400 mt-1">Todas as contas</p>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-slate-100 card-hover">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm text-slate-500 font-medium">Receitas do Mês</p>
                  <div className="w-9 h-9 bg-emerald-50 rounded-xl flex items-center justify-center">
                    <TrendingUp size={18} className="text-emerald-600" />
                  </div>
                </div>
                <p className="text-2xl font-bold text-emerald-600">{fmt(summary.income)}</p>
                <p className="text-xs text-slate-400 mt-1">
                  +{fmt(summary.pending_income)} pendente
                </p>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-slate-100 card-hover">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm text-slate-500 font-medium">Despesas do Mês</p>
                  <div className="w-9 h-9 bg-red-50 rounded-xl flex items-center justify-center">
                    <TrendingDown size={18} className="text-red-500" />
                  </div>
                </div>
                <p className="text-2xl font-bold text-red-500">{fmt(summary.expenses)}</p>
                <p className="text-xs text-slate-400 mt-1">
                  +{fmt(summary.pending_expenses)} a pagar
                </p>
              </div>

              <div className={`rounded-2xl p-6 border card-hover ${
                summary.net >= 0
                  ? 'bg-emerald-50 border-emerald-100'
                  : 'bg-red-50 border-red-100'
              }`}>
                <div className="flex items-center justify-between mb-3">
                  <p className={`text-sm font-medium ${summary.net >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                    Resultado
                  </p>
                  <span className="text-xl">{summary.net >= 0 ? '📈' : '📉'}</span>
                </div>
                <p className={`text-2xl font-bold ${summary.net >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                  {summary.net >= 0 ? '+' : ''}{fmt(summary.net)}
                </p>
                <p className={`text-xs mt-1 ${summary.net >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                  {summary.net >= 0 ? 'Mês positivo 🎉' : 'Atenção às despesas'}
                </p>
              </div>
            </div>

            {/* Charts row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Cash flow chart */}
              <div className="lg:col-span-2 bg-white rounded-2xl p-6 border border-slate-100">
                <h2 className="font-semibold text-slate-800 mb-4">Receitas vs Despesas (6 meses)</h2>
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={chartData} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
                      <defs>
                        <linearGradient id="colorIncome" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="colorExpenses" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                      <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }}
                        tickFormatter={(v) => `R$${(v/1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(v: number) => fmt(v)}
                        contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '12px' }}
                      />
                      <Legend wrapperStyle={{ fontSize: '12px' }} />
                      <Area type="monotone" dataKey="income" name="Receitas"
                        stroke="#10b981" fill="url(#colorIncome)" strokeWidth={2} />
                      <Area type="monotone" dataKey="expenses" name="Despesas"
                        stroke="#ef4444" fill="url(#colorExpenses)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[220px] flex items-center justify-center text-slate-400 text-sm">
                    Nenhum dado disponível ainda
                  </div>
                )}
              </div>

              {/* Top categories */}
              <div className="bg-white rounded-2xl p-6 border border-slate-100">
                <h2 className="font-semibold text-slate-800 mb-4">Maiores Despesas</h2>
                {summary.top_expense_categories.length > 0 ? (
                  <div className="space-y-3">
                    {summary.top_expense_categories.map((cat, i) => (
                      <div key={i}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-slate-600">{cat.category}</span>
                          <span className="text-sm font-medium text-slate-800">{fmt(cat.total)}</span>
                        </div>
                        <div className="w-full bg-slate-100 rounded-full h-1.5">
                          <div
                            className="bg-blue-500 h-1.5 rounded-full"
                            style={{ width: `${Math.min(cat.percentage || 0, 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-400 text-sm text-center py-8">
                    Nenhuma transação este mês
                  </p>
                )}

                <div className="mt-4 pt-4 border-t border-slate-100">
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Transações pagas: {summary.transaction_count.paid}</span>
                    <span className="text-amber-500">Pendentes: {summary.transaction_count.pending}</span>
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </AppLayout>
  )
}
