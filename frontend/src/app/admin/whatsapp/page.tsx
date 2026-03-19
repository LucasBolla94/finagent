'use client'
/**
 * WhatsApp Admin Page
 *
 * State machine:
 *   idle → connecting → qr_ready → connected
 *              ↓             ↓
 *           error ←─────── error
 *
 * Polling: while in qr_ready, polls /whatsapp/status every 4s.
 * Auto-retries status check with exponential backoff on network errors.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { adminApi } from '@/lib/adminApi'
import {
  Wifi, WifiOff, QrCode, RefreshCw, Loader2,
  CheckCircle2, AlertCircle, Smartphone, PlugZap, Unplug, Trash2,
  AlertTriangle,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

type PageState =
  | 'loading'       // Initial check
  | 'connected'     // open
  | 'qr_ready'      // QR code is available, waiting for scan
  | 'disconnected'  // Not connected, no QR
  | 'error'         // Evolution API unreachable or auth error

interface StatusResp {
  state: string | null
  status: string
  owner?: string
  detail?: string
}

interface ConnectResp {
  status: string
  state?: string
  qr_base64?: string
  owner?: string
  detail?: string
}

// ─── Constants ────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS   = 4_000   // Poll status every 4s while waiting for scan
const MAX_POLL_ATTEMPTS  = 75      // 75 × 4s = 5 minutes max wait
const STATUS_CONFIG = {
  loading:      { label: 'Verificando...', color: 'text-slate-500',   bg: 'bg-slate-50',   border: 'border-slate-200',  icon: Loader2 },
  connected:    { label: 'Conectado',      color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', icon: Wifi },
  qr_ready:     { label: 'Aguardando escaneamento', color: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-200', icon: QrCode },
  disconnected: { label: 'Desconectado',   color: 'text-red-700',     bg: 'bg-red-50',     border: 'border-red-200',    icon: WifiOff },
  error:        { label: 'Erro',           color: 'text-red-700',     bg: 'bg-red-50',     border: 'border-red-200',    icon: AlertCircle },
} as const

// ─── Flash toast ─────────────────────────────────────────────────────────────

type Flash = { type: 'ok' | 'warn' | 'err'; text: string }

// ─── Component ────────────────────────────────────────────────────────────────

export default function WhatsAppPage() {
  const [pageState, setPageState] = useState<PageState>('loading')
  const [qrBase64, setQrBase64]   = useState<string | null>(null)
  const [owner, setOwner]         = useState<string | null>(null)
  const [errorMsg, setErrorMsg]   = useState<string | null>(null)
  const [busy, setBusy]           = useState(false)
  const [flash, setFlash]         = useState<Flash | null>(null)
  const [pollCount, setPollCount] = useState(0)

  const pollRef     = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollAttempt = useRef(0)

  // ── Flash helper ──────────────────────────────────────────────────────────
  function showFlash(type: Flash['type'], text: string, ms = 7_000) {
    setFlash({ type, text })
    setTimeout(() => setFlash(null), ms)
  }

  // ── Stop polling ──────────────────────────────────────────────────────────
  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    pollAttempt.current = 0
    setPollCount(0)
  }, [])

  // ── Normalise state from /status response ─────────────────────────────────
  function applyStatus(res: StatusResp) {
    if (res.state === 'open') {
      setPageState('connected')
      setQrBase64(null)
      setOwner(res.owner ?? null)
      setErrorMsg(null)
      stopPoll()
      return
    }

    if (res.status === 'evolution_unreachable' || res.state === 'error') {
      setPageState('error')
      setErrorMsg(res.detail ?? 'Evolution API inacessível. Verifique se o container está rodando.')
      stopPoll()
      return
    }

    if (res.status === 'not_created' || res.state === null) {
      setPageState('disconnected')
      setErrorMsg(null)
      stopPoll()
      return
    }

    // connecting / close — keep qr_ready if we have a QR
    if (qrBase64) {
      setPageState('qr_ready')
    } else {
      setPageState('disconnected')
    }
  }

  // ── Check status ──────────────────────────────────────────────────────────
  const checkStatus = useCallback(async (silent = false) => {
    if (!silent) setPageState('loading')
    try {
      const res = await adminApi.whatsappStatus() as StatusResp
      applyStatus(res)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Erro de rede'
      if (!silent) {
        setPageState('error')
        setErrorMsg(msg)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qrBase64, stopPoll])

  // ── Mount: initial status check ───────────────────────────────────────────
  useEffect(() => {
    checkStatus()
    return () => stopPoll()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Polling: auto-poll while QR is displayed ──────────────────────────────
  useEffect(() => {
    if (pageState !== 'qr_ready') {
      stopPoll()
      return
    }

    if (pollRef.current) return // already polling

    pollRef.current = setInterval(async () => {
      pollAttempt.current += 1
      setPollCount(c => c + 1)

      if (pollAttempt.current >= MAX_POLL_ATTEMPTS) {
        stopPoll()
        showFlash('warn', 'QR Code expirou. Clique em "Novo QR Code" para gerar um novo.')
        return
      }

      try {
        const res = await adminApi.whatsappStatus() as StatusResp
        applyStatus(res)
      } catch {
        // Silent — network blip, keep trying
      }
    }, POLL_INTERVAL_MS)

    return () => stopPoll()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageState])

  // ── Connect / generate QR ─────────────────────────────────────────────────
  async function handleConnect() {
    setBusy(true)
    setErrorMsg(null)
    setFlash(null)
    stopPoll()

    try {
      const res = await adminApi.whatsappConnect() as ConnectResp

      if (res.status === 'connected') {
        setPageState('connected')
        setOwner(res.owner ?? null)
        setQrBase64(null)
        showFlash('ok', 'WhatsApp já está conectado!')
        return
      }

      if (res.status === 'qr_ready' && res.qr_base64) {
        setQrBase64(res.qr_base64)
        setPageState('qr_ready')
        showFlash('ok', 'QR Code gerado! Escaneie com o WhatsApp.')
        return
      }

      // Unexpected — show raw response for debugging
      showFlash('warn', `Resposta inesperada: ${JSON.stringify(res).slice(0, 120)}`)

    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Erro desconhecido'
      setPageState('error')
      setErrorMsg(msg)
      showFlash('err', msg)
    } finally {
      setBusy(false)
    }
  }

  // ── Refresh QR ────────────────────────────────────────────────────────────
  async function handleRefreshQR() {
    setBusy(true)
    stopPoll()
    try {
      const res = await adminApi.whatsappQRCode() as { status: string; qr_base64?: string; state?: string }

      if (res.status === 'connected' || res.state === 'open') {
        setPageState('connected')
        setQrBase64(null)
        showFlash('ok', 'WhatsApp conectado!')
        return
      }

      if (res.qr_base64) {
        setQrBase64(res.qr_base64)
        setPageState('qr_ready')
        pollAttempt.current = 0  // Reset poll counter on refresh
        showFlash('ok', 'QR Code atualizado.')
        return
      }

      showFlash('warn', 'QR Code não disponível no momento. Tente reconectar.')
    } catch (e) {
      showFlash('err', e instanceof Error ? e.message : 'Erro ao atualizar QR Code')
    } finally {
      setBusy(false)
    }
  }

  // ── Disconnect ────────────────────────────────────────────────────────────
  async function handleDisconnect() {
    if (!confirm('Desconectar o WhatsApp? O agente parará de receber mensagens.')) return
    setBusy(true)
    stopPoll()
    try {
      await adminApi.whatsappDisconnect()
      setPageState('disconnected')
      setQrBase64(null)
      setOwner(null)
      showFlash('ok', 'WhatsApp desconectado.')
    } catch (e) {
      showFlash('err', e instanceof Error ? e.message : 'Erro ao desconectar')
    } finally {
      setBusy(false)
    }
  }

  // ── Delete instance (nuclear option) ─────────────────────────────────────
  async function handleDeleteInstance() {
    if (!confirm('⚠️ Deletar completamente a instância WhatsApp?\n\nUse somente se estiver travada ou em estado inconsistente.')) return
    setBusy(true)
    stopPoll()
    try {
      await adminApi.whatsappDeleteInstance()
      setPageState('disconnected')
      setQrBase64(null)
      setOwner(null)
      showFlash('ok', 'Instância deletada. Clique em Conectar para recriar.')
    } catch (e) {
      showFlash('err', e instanceof Error ? e.message : 'Erro ao deletar instância')
    } finally {
      setBusy(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const cfg = STATUS_CONFIG[pageState]
  const StatusIcon = cfg.icon
  const instanceName = process.env.NEXT_PUBLIC_EVOLUTION_INSTANCE ?? 'finagent'

  return (
    <div className="p-6 max-w-2xl mx-auto">

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">WhatsApp</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          Instância:{' '}
          <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">
            {instanceName}
          </code>
        </p>
      </div>

      {/* Flash */}
      {flash && (
        <div className={`rounded-xl px-4 py-3 text-sm mb-5 flex items-center gap-2 border ${
          flash.type === 'err'  ? 'bg-red-50 text-red-700 border-red-200' :
          flash.type === 'warn' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                                  'bg-emerald-50 text-emerald-700 border-emerald-200'
        }`}>
          {flash.type === 'err'  ? <AlertCircle   size={15} className="flex-shrink-0" /> :
           flash.type === 'warn' ? <AlertTriangle  size={15} className="flex-shrink-0" /> :
                                   <CheckCircle2   size={15} className="flex-shrink-0" />}
          <span className="flex-1">{flash.text}</span>
          <button onClick={() => setFlash(null)} className="text-current opacity-40 hover:opacity-70 ml-2">✕</button>
        </div>
      )}

      {/* Status card */}
      <div className={`rounded-2xl border ${cfg.border} ${cfg.bg} p-6 mb-6`}>
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-white rounded-2xl flex items-center justify-center shadow-sm flex-shrink-0">
            <StatusIcon
              size={26}
              className={`${cfg.color} ${pageState === 'loading' ? 'animate-spin' : ''}`}
            />
          </div>
          <div className="flex-1 min-w-0">
            <p className={`font-bold text-lg ${cfg.color}`}>{cfg.label}</p>

            {pageState === 'connected' && owner && (
              <p className="text-sm text-emerald-600 mt-0.5 flex items-center gap-1.5">
                <Smartphone size={13} />
                {owner}
              </p>
            )}

            {pageState === 'qr_ready' && (
              <p className="text-sm text-amber-600 mt-0.5">
                Verificando a cada 4s ({pollCount}/{MAX_POLL_ATTEMPTS})
              </p>
            )}

            {pageState === 'disconnected' && (
              <p className="text-sm text-slate-500 mt-0.5">
                Nenhum número conectado. Clique em Conectar para gerar o QR Code.
              </p>
            )}

            {pageState === 'error' && errorMsg && (
              <p className="text-xs text-red-600 mt-1 break-words leading-relaxed">{errorMsg}</p>
            )}
          </div>

          {/* Refresh status button */}
          <button
            onClick={() => checkStatus()}
            disabled={busy}
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-white rounded-xl transition-all flex-shrink-0 disabled:opacity-40"
            title="Atualizar status"
          >
            <RefreshCw size={16} className={pageState === 'loading' ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* QR Code */}
      {pageState === 'qr_ready' && qrBase64 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 mb-6 text-center shadow-sm">
          <p className="text-sm font-semibold text-slate-700 mb-1">Escaneie com o WhatsApp</p>
          <p className="text-xs text-slate-400 mb-6">
            WhatsApp → Menu (3 pontos) → Aparelhos Conectados → Conectar aparelho
          </p>
          <div className="flex justify-center mb-6">
            {qrBase64.startsWith('data:image') ? (
              <img
                src={qrBase64}
                alt="QR Code WhatsApp"
                className="w-64 h-64 rounded-xl border-4 border-slate-100 object-contain"
              />
            ) : (
              /* Raw QR string — render via canvas or show as text */
              <div className="w-64 h-64 flex items-center justify-center bg-slate-50 rounded-xl border-4 border-slate-100">
                <p className="text-xs text-slate-500 text-center px-4 break-all">{qrBase64.slice(0, 80)}…</p>
              </div>
            )}
          </div>
          <button
            onClick={handleRefreshQR}
            disabled={busy}
            className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50 transition-colors mx-auto"
          >
            <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />
            Gerar novo QR Code
          </button>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3">
        {pageState === 'connected' ? (
          <>
            <button
              onClick={handleDisconnect}
              disabled={busy}
              className="flex items-center gap-2 bg-white border border-red-200 hover:bg-red-50 text-red-600 font-medium px-5 py-3 rounded-xl text-sm transition-all disabled:opacity-50"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Unplug size={16} />}
              Desconectar
            </button>
          </>
        ) : (
          <button
            onClick={pageState === 'qr_ready' ? handleRefreshQR : handleConnect}
            disabled={busy || pageState === 'loading'}
            className="flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-all shadow-sm"
          >
            {busy ? (
              <><Loader2 size={16} className="animate-spin" /> Aguarde...</>
            ) : pageState === 'qr_ready' ? (
              <><RefreshCw size={16} /> Novo QR Code</>
            ) : (
              <><PlugZap size={16} /> Conectar WhatsApp</>
            )}
          </button>
        )}
      </div>

      {/* How-to instructions */}
      {(pageState === 'disconnected' || pageState === 'qr_ready' || pageState === 'error') && (
        <div className="mt-8 bg-slate-50 rounded-2xl border border-slate-100 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-3">Como conectar:</p>
          <ol className="space-y-2 text-sm text-slate-600">
            {[
              <>Clique em <strong>Conectar WhatsApp</strong></>,
              <>Abra o WhatsApp no seu celular</>,
              <>Toque em <strong>Menu (⋮)</strong> → <strong>Aparelhos Conectados</strong></>,
              <>Toque em <strong>Conectar aparelho</strong></>,
              <>Aponte a câmera para o QR Code nesta tela</>,
            ].map((step, i) => (
              <li key={i} className="flex gap-2">
                <span className="font-bold text-emerald-600 flex-shrink-0 w-5">{i + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Nuclear option */}
      {(pageState === 'error' || pageState === 'disconnected') && (
        <div className="mt-4">
          <details className="group">
            <summary className="text-xs text-slate-400 cursor-pointer select-none hover:text-slate-600 transition-colors">
              ▸ Opções avançadas (usar somente se a instância estiver travada)
            </summary>
            <div className="mt-3 bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-xs text-red-700 mb-3">
                Se a instância estiver em estado inconsistente, delete-a e reconecte do zero. Isso não apaga conversas no celular.
              </p>
              <button
                onClick={handleDeleteInstance}
                disabled={busy}
                className="flex items-center gap-2 text-xs text-red-600 hover:text-red-800 font-medium border border-red-300 bg-white px-3 py-2 rounded-lg transition-all disabled:opacity-50"
              >
                <Trash2 size={13} />
                Deletar instância e reiniciar do zero
              </button>
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
