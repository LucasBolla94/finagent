'use client'
import { useEffect, useState } from 'react'
import AppLayout from '@/components/layout/AppLayout'
import { reports, ApiError } from '@/lib/api'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell
} from 'recharts'

function fmt(v: number) {
  return (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function fmtMonth(s: string) {
  return new Date(s + 'T12:00:00').toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316']

export default function ReportsPage() {
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null)
  const [cashFlow, setCashFlow] = useState<Array<Record<string, unknown>>>([])
  const [categories, setCategories] = useState<Array<Record<string, unknown>>>([])
  const [tab, setTab] = useState<'summary' | 'cashflow' | 'categories'>('summary')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [sum, cf, cat] = await Promise.all([
          reports.summary(),
          reports.cashFlow(6),
          reports.byCategory(),
        ])
        setSummary(sum)
        setCashFlow((cf as { cash_flow: Array<Record<string, unknown>> }).cash_flow || [])
        setCategories((cat as { categories: Array<Record<string, unknown>> }).categories || [])
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const cfData = cashFlow.map(item => ({
    name: fmtMonth(item.month as string),
    Receitas: item.income,
    Despesas: item.expenses,
    Resultado: item.net,
  }))

  return (
    <AppLayout>
      <div className="p-6 lg:p-8 max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-800">Relatórios</h1>
          <p className="text-slate-500 text-sm mt-0.5">Análise financeira completa</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit mb-6">
          {(['summary', 'cashflow', 'categories'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                tab === t ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
              }`}>
              {{ summary: 'Resumo', cashflow: 'Fluxo de Caixa', categories: 'Por Categoria' }[t]}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="bg-white rounded-2xl border border-slate-100 h-64 flex items-center justify-center">
            <p className="text-slate-400 text-sm">Carregando...</p>
          </div>
        ) : (
          <>
            {/* Summary tab */}
            {tab === 'summary' && summary && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-6">
                  <p className="text-sm text-emerald-700 font-medium mb-2">Receitas do Mês</p>
                  <p className="text-3xl font-bold text-emerald-700">{fmt(summary.income as number)}</p>
                  <p className="text-xs text-emerald-600 mt-2">+ {fmt(summary.pending_income as number)} pendente</p>
                </div>
                <div className="bg-red-50 border border-red-100 rounded-2xl p-6">
                  <p className="text-sm text-red-700 font-medium mb-2">Despesas do Mês</p>
                  <p className="text-3xl font-bold text-red-600">{fmt(summary.expenses as number)}</p>
                  <p className="text-xs text-red-500 mt-2">+ {fmt(summary.pending_expenses as number)} a pagar</p>
                </div>
                <div className={`${(summary.net as number) >= 0 ? 'bg-blue-50 border-blue-100' : 'bg-orange-50 border-orange-100'} border rounded-2xl p-6`}>
                  <p className={`text-sm font-medium mb-2 ${(summary.net as number) >= 0 ? 'text-blue-700' : 'text-orange-700'}`}>Resultado Líquido</p>
                  <p className={`text-3xl font-bold ${(summary.net as number) >= 0 ? 'text-blue-700' : 'text-orange-600'}`}>
                    {(summary.net as number) >= 0 ? '+' : ''}{fmt(summary.net as number)}
                  </p>
                  <p className={`text-xs mt-2 ${(summary.net as number) >= 0 ? 'text-blue-600' : 'text-orange-500'}`}>
                    {(summary.net as number) >= 0 ? '✅ Saldo positivo' : '⚠️ Despesas > Receitas'}
                  </p>
                </div>
              </div>
            )}

            {/* Cash flow tab */}
            {tab === 'cashflow' && (
              <div className="bg-white rounded-2xl border border-slate-100 p-6">
                <h2 className="font-semibold text-slate-800 mb-6">Fluxo de Caixa — Últimos 6 Meses</h2>
                {cfData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={cfData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                      <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }}
                        tickFormatter={v => `R$${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(v: number) => fmt(v)}
                        contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '12px' }}
                      />
                      <Legend wrapperStyle={{ fontSize: '12px' }} />
                      <Bar dataKey="Receitas" fill="#10b981" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Despesas" fill="#ef4444" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
                    Sem dados suficientes
                  </div>
                )}
              </div>
            )}

            {/* Categories tab */}
            {tab === 'categories' && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white rounded-2xl border border-slate-100 p-6">
                  <h2 className="font-semibold text-slate-800 mb-4">Distribuição de Despesas</h2>
                  {categories.length > 0 ? (
                    <ResponsiveContainer width="100%" height={260}>
                      <PieChart>
                        <Pie data={categories} cx="50%" cy="50%" outerRadius={100}
                          dataKey="total" nameKey="category" label={({ category, percentage }) => `${category} ${(percentage ?? 0).toFixed(0)}%`}
                          labelLine={false} fontSize={11}>
                          {categories.map((_, i) => (
                            <Cell key={i} fill={COLORS[i % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: number) => fmt(v)} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
                      Sem categorias este mês
                    </div>
                  )}
                </div>
                <div className="bg-white rounded-2xl border border-slate-100 p-6">
                  <h2 className="font-semibold text-slate-800 mb-4">Detalhamento</h2>
                  <div className="space-y-3">
                    {categories.map((cat, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                        <div className="flex-1 min-w-0">
                          <div className="flex justify-between items-baseline mb-1">
                            <span className="text-sm text-slate-700 truncate">{cat.category as string}</span>
                            <span className="text-sm font-semibold text-slate-800 ml-2">{fmt(cat.total as number)}</span>
                          </div>
                          <div className="w-full bg-slate-100 rounded-full h-1.5">
                            <div className="h-1.5 rounded-full" style={{ width: `${Math.min(cat.percentage as number || 0, 100)}%`, background: COLORS[i % COLORS.length] }} />
                          </div>
                        </div>
                        <span className="text-xs text-slate-400 w-12 text-right flex-shrink-0">
                          {(cat.percentage as number || 0).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  )
}
