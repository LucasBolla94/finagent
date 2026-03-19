'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { adminApi, getAdminKey, setAdminKey } from '@/lib/adminApi'
import { Shield, Eye, EyeOff, Loader2 } from 'lucide-react'

export default function AdminLoginPage() {
  const router = useRouter()
  const [key, setKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    // Already logged in? Go to dashboard
    if (getAdminKey()) {
      router.replace('/admin')
    }
  }, [])

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    if (!key.trim()) return
    setLoading(true)
    setError('')
    setAdminKey(key.trim())
    try {
      await adminApi.stats()  // validate key against real endpoint
      router.replace('/admin')
    } catch {
      setError('Chave inválida ou servidor inacessível. Verifique o ADMIN_SECRET_KEY no .env')
      setAdminKey('')  // clear invalid key
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-blue-600/30">
            <Shield size={30} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">FinAgent</h1>
          <p className="text-slate-400 text-sm mt-1">Painel de Administração</p>
        </div>

        {/* Card */}
        <div className="bg-slate-800/80 backdrop-blur border border-slate-700 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-white font-semibold text-lg mb-1">Entrar</h2>
          <p className="text-slate-400 text-sm mb-6">Use sua chave de admin do arquivo <code className="text-blue-400 bg-slate-700 px-1 rounded text-xs">.env</code></p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-2">
                ADMIN_SECRET_KEY
              </label>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={key}
                  onChange={e => { setKey(e.target.value); setError('') }}
                  placeholder="admin123"
                  autoFocus
                  className="w-full bg-slate-700 border border-slate-600 rounded-xl px-4 py-3 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                >
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="bg-red-900/30 border border-red-700/50 rounded-xl px-4 py-3 text-red-400 text-xs">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !key.trim()}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-xl transition-all text-sm shadow-lg shadow-blue-600/20"
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Verificando...
                </>
              ) : (
                'Entrar no painel'
              )}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-slate-700">
            <p className="text-xs text-slate-500 text-center">
              Em dev, a chave padrão é{' '}
              <button
                onClick={() => setKey('admin123')}
                className="text-blue-400 hover:text-blue-300 font-mono underline"
              >
                admin123
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
