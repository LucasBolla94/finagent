'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { adminApi } from '@/lib/adminApi'
import {
  Users, Bot, FileText, MessageSquare, ChevronRight,
  QrCode, Wifi, WifiOff, RefreshCw, TrendingUp
} from 'lucide-react'

type Stats = {
  active_clients: number
  active_agents: number
  imported_documents: number
  messages_today: number
  whatsapp_state: string | null
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => { load() }, [])

  async function load(refresh = false) {
    if (refresh) setRefreshing(true)
    try {
      const s = await adminApi.stats() as Stats
      setStats(s)
    } catch (e) {
      console.error('Failed to load stats:', e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const waConnected = stats?.whatsapp_state === 'open'

  const STAT_CARDS = [
    {
      label: 'Clientes ativos',
      value: stats?.active_clients ?? '–',
      icon: Users,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
    },
    {
      label: 'Agentes ativos',
      value: stats?.active_agents ?? '–',
      icon: Bot,
      color: 'text-purple-600',
      bg: 'bg-purple-50',
    },
    {
      label: 'Mensagens hoje',
      value: stats?.messages_today ?? '–',
      icon: TrendingUp,
      color: 'text-emerald-600',
      bg: 'bg-emerald-50',
    },
    {
      label: 'Docs importados',
      value: stats?.imported_documents ?? '–',
      icon: FileText,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
    },
  ]

  const MODULES = [
    {
      href: '/admin/whatsapp',
      title: 'WhatsApp',
      desc: waConnected ? '🟢 Conectado' : '🔴 Desconectado',
      icon: QrCode,
      color: 'text-emerald-600',
      bg: 'bg-emerald-50',
    },
    {
      href: '/admin/agents',
      title: 'Gerenciar Agentes',
      desc: `${stats?.active_agents ?? 0} agente(s) ativo(s)`,
      icon: Bot,
      color: 'text-purple-600',
      bg: 'bg-purple-50',
    },
    {
      href: '/admin/tenants',
      title: 'Clientes',
      desc: `${stats?.active_clients ?? 0} cliente(s) ativo(s)`,
      icon: Users,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
    },
  ]

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header row */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Dashboard</h1>
          <p className="text-slate-500 text-sm mt-0.5">Visão geral do sistema</p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-800 bg-white border border-slate-200 px-3 py-2 rounded-xl transition-all hover:shadow-sm"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Atualizar
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {STAT_CARDS.map(card => {
          const Icon = card.icon
          return (
            <div key={card.label} className="bg-white rounded-2xl border border-slate-100 p-5 hover:shadow-sm transition-all">
              <div className={`w-10 h-10 ${card.bg} rounded-xl flex items-center justify-center mb-3`}>
                <Icon size={18} className={card.color} />
              </div>
              {loading ? (
                <div className="h-8 w-12 bg-slate-100 animate-pulse rounded-lg mb-1" />
              ) : (
                <p className={`text-3xl font-bold ${card.color}`}>{card.value}</p>
              )}
              <p className="text-xs text-slate-500 mt-1">{card.label}</p>
            </div>
          )
        })}
      </div>

      {/* WhatsApp status banner */}
      {!loading && (
        <div className={`rounded-2xl border p-4 mb-8 flex items-center justify-between ${
          waConnected
            ? 'bg-emerald-50 border-emerald-200'
            : 'bg-amber-50 border-amber-200'
        }`}>
          <div className="flex items-center gap-3">
            {waConnected
              ? <Wifi size={20} className="text-emerald-600" />
              : <WifiOff size={20} className="text-amber-600" />
            }
            <div>
              <p className={`font-semibold text-sm ${waConnected ? 'text-emerald-800' : 'text-amber-800'}`}>
                WhatsApp {waConnected ? 'Conectado' : 'Desconectado'}
              </p>
              <p className={`text-xs ${waConnected ? 'text-emerald-600' : 'text-amber-600'}`}>
                {waConnected
                  ? 'O agente está recebendo mensagens normalmente'
                  : 'O agente não está recebendo mensagens. Conecte o WhatsApp.'}
              </p>
            </div>
          </div>
          <Link
            href="/admin/whatsapp"
            className={`text-sm font-medium px-4 py-2 rounded-xl transition-all ${
              waConnected
                ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
                : 'bg-amber-600 hover:bg-amber-700 text-white'
            }`}
          >
            {waConnected ? 'Gerenciar' : 'Conectar'}
          </Link>
        </div>
      )}

      {/* Module cards */}
      <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">Seções</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {MODULES.map(m => {
          const Icon = m.icon
          return (
            <Link
              key={m.href}
              href={m.href}
              className="bg-white rounded-2xl border border-slate-100 p-6 hover:shadow-md hover:-translate-y-0.5 transition-all group"
            >
              <div className={`w-12 h-12 ${m.bg} rounded-2xl flex items-center justify-center mb-4`}>
                <Icon size={22} className={m.color} />
              </div>
              <p className="font-semibold text-slate-800">{m.title}</p>
              <p className="text-sm text-slate-500 mt-0.5">{m.desc}</p>
              <div className="flex items-center gap-1 text-blue-600 text-xs font-medium mt-4 group-hover:gap-2 transition-all">
                Acessar <ChevronRight size={14} />
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
