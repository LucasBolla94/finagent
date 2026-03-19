'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { adminApi, getAdminKey, setAdminKey, clearAdminKey } from '@/lib/adminApi'
import { Users, Bot, FileText, ChevronRight, QrCode, Shield, LogOut } from 'lucide-react'

export default function AdminPage() {
  const router = useRouter()
  const [keyInput, setKeyInput] = useState('')
  const [authenticated, setAuthenticated] = useState(false)
  const [stats, setStats] = useState<{ active_clients: number; active_agents: number; imported_documents: number } | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const key = getAdminKey()
    if (key) tryAuth(key)
  }, [])

  async function tryAuth(key?: string) {
    const k = key || keyInput
    if (!k) return
    setAdminKey(k)
    setLoading(true)
    setError('')
    try {
      const s = await adminApi.stats()
      setStats(s)
      setAuthenticated(true)
    } catch (e) {
      setError('Chave inválida ou servidor inacessível')
      clearAdminKey()
    } finally {
      setLoading(false)
    }
  }

  function logout() {
    clearAdminKey()
    setAuthenticated(false)
    setStats(null)
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
        <div className="bg-slate-800 rounded-2xl p-8 w-full max-w-sm border border-slate-700">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
              <Shield size={20} className="text-white" />
            </div>
            <div>
              <p className="font-bold text-white">Admin FinAgent</p>
              <p className="text-xs text-slate-400">Acesso restrito</p>
            </div>
          </div>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Chave de Admin</label>
              <input
                type="password"
                value={keyInput}
                onChange={e => setKeyInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && tryAuth()}
                placeholder="Sua ADMIN_SECRET_KEY do .env"
                className="w-full bg-slate-700 border border-slate-600 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {error && <p className="text-red-400 text-xs">{error}</p>}
            <button
              onClick={() => tryAuth()}
              disabled={loading || !keyInput}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl transition-all text-sm"
            >
              {loading ? 'Verificando...' : 'Entrar'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  const MODULES = [
    {
      href: '/admin/agents',
      title: 'Gerenciar Agentes',
      desc: `${stats?.active_agents || 0} agentes ativos`,
      icon: Bot,
      color: 'bg-purple-50 text-purple-600',
    },
    {
      href: '/admin/whatsapp',
      title: 'WhatsApp',
      desc: 'Conectar via QR Code',
      icon: QrCode,
      color: 'bg-emerald-50 text-emerald-600',
    },
    {
      href: '/admin/tenants',
      title: 'Clientes',
      desc: `${stats?.active_clients || 0} clientes ativos`,
      icon: Users,
      color: 'bg-blue-50 text-blue-600',
    },
  ]

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-100 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center">
            <Shield size={18} className="text-white" />
          </div>
          <div>
            <p className="font-bold text-slate-800">Admin Panel</p>
            <p className="text-xs text-slate-400">FinAgent</p>
          </div>
        </div>
        <button onClick={logout} className="flex items-center gap-2 text-sm text-slate-500 hover:text-red-500 transition-colors">
          <LogOut size={16} />
          Sair
        </button>
      </div>

      <div className="p-6 max-w-4xl mx-auto">
        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div className="bg-white rounded-2xl border border-slate-100 p-5 text-center">
              <p className="text-3xl font-bold text-blue-600">{stats.active_clients}</p>
              <p className="text-sm text-slate-500 mt-1">Clientes</p>
            </div>
            <div className="bg-white rounded-2xl border border-slate-100 p-5 text-center">
              <p className="text-3xl font-bold text-purple-600">{stats.active_agents}</p>
              <p className="text-sm text-slate-500 mt-1">Agentes</p>
            </div>
            <div className="bg-white rounded-2xl border border-slate-100 p-5 text-center">
              <p className="text-3xl font-bold text-emerald-600">{stats.imported_documents}</p>
              <p className="text-sm text-slate-500 mt-1">Documentos</p>
            </div>
          </div>
        )}

        {/* Modules */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {MODULES.map(m => {
            const Icon = m.icon
            return (
              <Link key={m.href} href={m.href}
                className="bg-white rounded-2xl border border-slate-100 p-6 hover:shadow-md hover:-translate-y-0.5 transition-all group">
                <div className={`w-12 h-12 rounded-2xl ${m.color} flex items-center justify-center mb-4`}>
                  <Icon size={22} />
                </div>
                <p className="font-semibold text-slate-800">{m.title}</p>
                <p className="text-sm text-slate-500 mt-0.5">{m.desc}</p>
                <div className="flex items-center gap-1 text-blue-600 text-xs font-medium mt-3 group-hover:gap-2 transition-all">
                  Acessar <ChevronRight size={14} />
                </div>
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  )
}
