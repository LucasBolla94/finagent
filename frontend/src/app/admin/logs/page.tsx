'use client'
/**
 * System Logs — /admin/logs
 *
 * Shows all backend log entries stored in system_logs table.
 * Supports filtering by level, service, and free-text search.
 * Auto-refreshes every 15s. Clicking a row expands full details JSON.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { adminApi } from '@/lib/adminApi'
import {
  RefreshCw, Search, AlertCircle, AlertTriangle,
  Info, Bug, ChevronDown, ChevronRight, Trash2, X,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface LogEntry {
  id: number
  created_at: string
  level: string
  service: string
  event: string | null
  message: string
  details: Record<string, unknown> | null
  duration_ms: number | null
  user_id: string | null
}

// ─── Constants ────────────────────────────────────────────────────────────────

const LEVELS = ['', 'ERROR', 'WARNING', 'INFO', 'DEBUG'] as const
const SERVICES = ['', 'whatsapp', 'auth', 'admin', 'celery', 'agent'] as const
const PAGE_SIZE = 100
const AUTO_REFRESH_S = 15

// ─── Level badge ──────────────────────────────────────────────────────────────

const LEVEL_STYLES: Record<string, string> = {
  ERROR:   'bg-red-100 text-red-800 border border-red-300',
  WARNING: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
  INFO:    'bg-blue-100 text-blue-700 border border-blue-300',
  DEBUG:   'bg-gray-100 text-gray-600 border border-gray-300',
}

const LEVEL_ICONS: Record<string, React.ReactNode> = {
  ERROR:   <AlertCircle   size={12} className="inline mr-1" />,
  WARNING: <AlertTriangle size={12} className="inline mr-1" />,
  INFO:    <Info          size={12} className="inline mr-1" />,
  DEBUG:   <Bug           size={12} className="inline mr-1" />,
}

function LevelBadge({ level }: { level: string }) {
  const cls = LEVEL_STYLES[level] || 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${cls}`}>
      {LEVEL_ICONS[level]}
      {level}
    </span>
  )
}

// ─── Row ──────────────────────────────────────────────────────────────────────

function LogRow({ entry }: { entry: LogEntry }) {
  const [open, setOpen] = useState(false)

  const ts = new Date(entry.created_at)
  const time = ts.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const dateStr = ts.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })

  const hasDetails = entry.details && Object.keys(entry.details).length > 0

  return (
    <>
      <tr
        className={`border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors
          ${entry.level === 'ERROR' ? 'bg-red-50/30' : ''}
          ${entry.level === 'WARNING' ? 'bg-yellow-50/20' : ''}
        `}
        onClick={() => hasDetails && setOpen(p => !p)}
        title={hasDetails ? 'Clique para ver detalhes' : undefined}
      >
        {/* Time */}
        <td className="px-3 py-2 text-xs text-gray-400 whitespace-nowrap font-mono">
          <span className="text-gray-500">{dateStr}</span>{' '}
          <span className="text-gray-700">{time}</span>
        </td>
        {/* Level */}
        <td className="px-3 py-2 whitespace-nowrap">
          <LevelBadge level={entry.level} />
        </td>
        {/* Service */}
        <td className="px-3 py-2 text-xs font-medium text-indigo-700 whitespace-nowrap">
          {entry.service}
        </td>
        {/* Event */}
        <td className="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">
          {entry.event || '—'}
        </td>
        {/* Message */}
        <td className="px-3 py-2 text-sm text-gray-800 max-w-lg truncate">
          {entry.message}
        </td>
        {/* Duration */}
        <td className="px-3 py-2 text-xs text-gray-400 whitespace-nowrap text-right">
          {entry.duration_ms != null ? `${entry.duration_ms}ms` : ''}
        </td>
        {/* Expand icon */}
        <td className="px-2 py-2 text-gray-400">
          {hasDetails
            ? open
              ? <ChevronDown size={14} />
              : <ChevronRight size={14} />
            : null
          }
        </td>
      </tr>
      {open && hasDetails && (
        <tr className="bg-gray-900">
          <td colSpan={7} className="px-4 py-3">
            <pre className="text-xs text-green-300 font-mono overflow-auto max-h-64 whitespace-pre-wrap">
              {JSON.stringify(entry.details, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LogsPage() {
  const [logs, setLogs]         = useState<LogEntry[]>([])
  const [total, setTotal]       = useState(0)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [offset, setOffset]     = useState(0)

  // Filters
  const [level,   setLevel]     = useState('')
  const [service, setService]   = useState('')
  const [search,  setSearch]    = useState('')
  const [searchInput, setSearchInput] = useState('')

  // Auto-refresh countdown
  const [countdown, setCountdown] = useState(AUTO_REFRESH_S)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Clear-logs modal
  const [showClear, setShowClear] = useState(false)
  const [clearing, setClearing]  = useState(false)

  const fetchLogs = useCallback(async (off = offset) => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminApi.getLogs({
        level:   level   || undefined,
        service: service || undefined,
        search:  search  || undefined,
        limit:   PAGE_SIZE,
        offset:  off,
      })
      setLogs(data.logs)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao carregar logs')
    } finally {
      setLoading(false)
    }
  }, [level, service, search, offset])

  // Auto-refresh
  useEffect(() => {
    fetchLogs(0)
    setOffset(0)
    setCountdown(AUTO_REFRESH_S)

    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) {
          fetchLogs(0)
          return AUTO_REFRESH_S
        }
        return c - 1
      })
    }, 1000)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, service, search])

  const handleSearch = () => {
    setSearch(searchInput)
    setOffset(0)
  }

  const handleClearSearch = () => {
    setSearchInput('')
    setSearch('')
    setOffset(0)
  }

  const handleClearLogs = async () => {
    setClearing(true)
    try {
      const r = await adminApi.clearLogs(30)
      alert(`Deletados ${r.deleted} registros com mais de 30 dias.`)
      setShowClear(false)
      fetchLogs(0)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Erro')
    } finally {
      setClearing(false)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  const errorCount   = logs.filter(l => l.level === 'ERROR').length
  const warningCount = logs.filter(l => l.level === 'WARNING').length

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Logs do Sistema</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {total} registros · atualiza em {countdown}s
              {errorCount > 0 && (
                <span className="ml-3 text-red-600 font-semibold">
                  ⚠ {errorCount} erro{errorCount > 1 ? 's' : ''} nesta página
                </span>
              )}
              {warningCount > 0 && (
                <span className="ml-2 text-yellow-600 font-semibold">
                  {warningCount} aviso{warningCount > 1 ? 's' : ''}
                </span>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => { fetchLogs(offset); setCountdown(AUTO_REFRESH_S) }}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Atualizar
            </button>
            <button
              onClick={() => setShowClear(true)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-red-50 border border-red-200 text-red-700 rounded-lg hover:bg-red-100 transition-colors"
            >
              <Trash2 size={14} />
              Limpar antigos
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white border border-gray-200 rounded-xl p-4 mb-4 flex flex-wrap gap-3 items-end">
          {/* Level */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Nível</label>
            <select
              value={level}
              onChange={e => { setLevel(e.target.value); setOffset(0) }}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {LEVELS.map(l => (
                <option key={l} value={l}>{l || 'Todos'}</option>
              ))}
            </select>
          </div>

          {/* Service */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Serviço</label>
            <select
              value={service}
              onChange={e => { setService(e.target.value); setOffset(0) }}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {SERVICES.map(s => (
                <option key={s} value={s}>{s || 'Todos'}</option>
              ))}
            </select>
          </div>

          {/* Search */}
          <div className="flex-1 min-w-52">
            <label className="block text-xs font-medium text-gray-500 mb-1">Buscar mensagem</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  placeholder="ex: count:0, QR, timeout..."
                  className="w-full border border-gray-300 rounded-lg pl-3 pr-8 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                {searchInput && (
                  <button
                    onClick={handleClearSearch}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
              <button
                onClick={handleSearch}
                className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm transition-colors"
              >
                <Search size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-4 flex items-center gap-2">
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {/* Table */}
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Horário</th>
                  <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Nível</th>
                  <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Serviço</th>
                  <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Evento</th>
                  <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Mensagem</th>
                  <th className="px-3 py-2.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Duração</th>
                  <th className="px-2 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {loading && logs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                      <RefreshCw size={20} className="animate-spin mx-auto mb-2" />
                      Carregando logs...
                    </td>
                  </tr>
                ) : logs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                      Nenhum log encontrado
                    </td>
                  </tr>
                ) : (
                  logs.map(entry => <LogRow key={entry.id} entry={entry} />)
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="border-t border-gray-200 px-4 py-3 flex items-center justify-between bg-gray-50">
              <span className="text-xs text-gray-500">
                Página {currentPage} de {totalPages} · {total} registros
              </span>
              <div className="flex gap-2">
                <button
                  disabled={offset === 0}
                  onClick={() => { const o = Math.max(0, offset - PAGE_SIZE); setOffset(o); fetchLogs(o) }}
                  className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg hover:bg-white disabled:opacity-40 transition-colors"
                >
                  ← Anterior
                </button>
                <button
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => { const o = offset + PAGE_SIZE; setOffset(o); fetchLogs(o) }}
                  className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg hover:bg-white disabled:opacity-40 transition-colors"
                >
                  Próxima →
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer hint */}
        <p className="text-xs text-gray-400 mt-3 text-center">
          Clique em qualquer linha com detalhes para expandir o JSON completo · Logs expiram após 30 dias
        </p>
      </div>

      {/* Clear Logs Modal */}
      {showClear && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-gray-900 mb-2">Limpar logs antigos?</h3>
            <p className="text-sm text-gray-600 mb-5">
              Todos os registros com mais de <strong>30 dias</strong> serão deletados permanentemente.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowClear(false)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-xl text-sm hover:bg-gray-50 transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleClearLogs}
                disabled={clearing}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-xl text-sm hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {clearing ? 'Deletando...' : 'Confirmar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
