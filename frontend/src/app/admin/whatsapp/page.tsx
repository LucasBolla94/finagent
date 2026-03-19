'use client'
import { useState, useEffect, useRef } from 'react'
import { adminApi } from '@/lib/adminApi'
import {
  Wifi, WifiOff, QrCode, RefreshCw, Loader2,
  CheckCircle2, AlertCircle, Smartphone, PlugZap, Unplug, Trash2
} from 'lucide-react'

type WaState = 'loading' | 'connected' | 'qr_pending' | 'disconnected' | 'error'

type StatusResponse = {
  state: string | null
  status: string
  owner?: string
  detail?: string
}

export default function WhatsAppPage() {
  const [waState, setWaState] = useState<WaState>('loading')
  const [qrBase64, setQrBase64] = useState<string | null>(null)
  const [owner, setOwner] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [flash, setFlash] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    fetchStatus()
    return () => stopPoll()
  }, [])

  // Auto-poll every 5s while QR is showing — stop when connected
  useEffect(() => {
    if (waState === 'qr_pending') {
      stopPoll()
      pollRef.current = setInterval(fetchStatus, 5000)
    } else {
      stopPoll()
    }
  }, [waState])

  function stopPoll() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  function showFlash(type: 'ok' | 'err', text: string) {
    setFlash({ type, text })
    setTimeout(() => setFlash(null), 6000)
  }

  async function fetchStatus() {
    try {
      const res = await adminApi.whatsappStatus() as StatusResponse
      const state = res.state

      if (state === 'open') {
        setWaState('connected')
        setQrBase64(null)
        setOwner(res.owner || null)
        setErrorMsg(null)
      } else if (state === null || res.status === 'not_created') {
        setWaState('disconnected')
        setErrorMsg(null)
      } else if (state === 'error' || res.status === 'evolution_unreachable') {
        setWaState('error')
        setErrorMsg(res.detail || 'Evolution API inacessível')
      } else {
        // connecting / close
        setWaState('disconnected')
        setErrorMsg(null)
      }
    } catch (e) {
      setWaState('error')
      setErrorMsg(e instanceof Error ? e.message : 'Erro ao verificar status')
    }
  }

  async function handleConnect() {
    setLoading(true)
    setErrorMsg(null)
    setFlash(null)
    try {
      const res = await adminApi.whatsappConnect() as {
        status: string
        state?: string
        qr_base64?: string
        owner?: string
      }

      if (res.status === 'connected') {
        setWaState('connected')
        setOwner(res.owner || null)
        setQrBase64(null)
        showFlash('ok', 'WhatsApp já está conectado!')
        return
      }

      if (res.status === 'qr_ready' && res.qr_base64) {
        setQrBase64(res.qr_base64)
        setWaState('qr_pending')
        showFlash('ok', 'QR Code gerado! Escaneie com o WhatsApp.')
        return
      }

      // Unexpected response
      showFlash('err', `Resposta inesperada: ${JSON.stringify(res).slice(0, 100)}`)

    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Erro desconhecido'
      setErrorMsg(msg)
      showFlash('err', msg)
    } finally {
      setLoading(false)
    }
  }

  async function handleRefreshQR() {
    setLoading(true)
    try {
      const res = await adminApi.whatsappQRCode() as { status: string; qr_base64?: string; state?: string }
      if (res.status === 'connected' || res.state === 'open') {
        setWaState('connected')
        setQrBase64(null)
        showFlash('ok', 'WhatsApp conectado!')
        return
      }
      if (res.qr_base64) {
        setQrBase64(res.qr_base64)
        setWaState('qr_pending')
        showFlash('ok', 'QR Code atualizado.')
      }
    } catch (e) {
      showFlash('err', e instanceof Error ? e.message : 'Erro ao atualizar QR Code')
    } finally {
      setLoading(false)
    }
  }

  async function handleDisconnect() {
    if (!confirm('Desconectar o WhatsApp? O agente parará de receber mensagens.')) return
    setLoading(true)
    try {
      await adminApi.whatsappDisconnect()
      setWaState('disconnected')
      setQrBase64(null)
      setOwner(null)
      showFlash('ok', 'WhatsApp desconectado com sucesso.')
    } catch (e) {
      showFlash('err', e instanceof Error ? e.message : 'Erro ao desconectar')
    } finally {
      setLoading(false)
    }
  }

  async function handleDeleteInstance() {
    if (!confirm('⚠️ Deletar completamente a instância WhatsApp? Use isso somente se estiver travada.')) return
    setLoading(true)
    try {
      await adminApi.whatsappDeleteInstance()
      setWaState('disconnected')
      setQrBase64(null)
      setOwner(null)
      showFlash('ok', 'Instância deletada. Você pode criar uma nova agora.')
    } catch (e) {
      showFlash('err', e instanceof Error ? e.message : 'Erro ao deletar instância')
    } finally {
      setLoading(false)
    }
  }

  // ── Status card config ────────────────────────────────────────────────────
  const STATUS_CONFIG = {
    loading:       { label: 'Verificando...', color: 'text-slate-500',   bg: 'bg-slate-50',   border: 'border-slate-200',  Icon: Loader2 },
    connected:     { label: 'Conectado',      color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', Icon: Wifi },
    qr_pending:    { label: 'Aguardando escaneamento', color: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-200', Icon: QrCode },
    disconnected:  { label: 'Desconectado',   color: 'text-red-700',     bg: 'bg-red-50',     border: 'border-red-200',    Icon: WifiOff },
    error:         { label: 'Erro',           color: 'text-red-700',     bg: 'bg-red-50',     border: 'border-red-200',    Icon: AlertCircle },
  }

  const cfg = STATUS_CONFIG[waState]
  const StatusIcon = cfg.Icon

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">WhatsApp</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          Instância: <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">{
            process.env.NEXT_PUBLIC_EVOLUTION_INSTANCE || 'finagent_agent1'
          }</code>
        </p>
      </div>

      {/* Flash message */}
      {flash && (
        <div className={`rounded-xl px-4 py-3 text-sm mb-6 flex items-center gap-2 ${
          flash.type === 'err'
            ? 'bg-red-50 text-red-700 border border-red-200'
            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        }`}>
          {flash.type === 'err' ? <AlertCircle size={15} className="flex-shrink-0" /> : <CheckCircle2 size={15} className="flex-shrink-0" />}
          <span className="flex-1">{flash.text}</span>
        </div>
      )}

      {/* Status card */}
      <div className={`rounded-2xl border ${cfg.border} ${cfg.bg} p-6 mb-6`}>
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-white rounded-2xl flex items-center justify-center shadow-sm flex-shrink-0">
            <StatusIcon
              size={26}
              className={`${cfg.color} ${waState === 'loading' ? 'animate-spin' : ''}`}
            />
          </div>
          <div className="flex-1 min-w-0">
            <p className={`font-bold text-lg ${cfg.color}`}>{cfg.label}</p>
            {waState === 'connected' && owner && (
              <p className="text-sm text-emerald-600 mt-0.5 flex items-center gap-1.5">
                <Smartphone size={13} />
                {owner}
              </p>
            )}
            {waState === 'qr_pending' && (
              <p className="text-sm text-amber-600 mt-0.5">
                Verificando status a cada 5s...
              </p>
            )}
            {waState === 'disconnected' && (
              <p className="text-sm text-slate-500 mt-0.5">
                O agente não está recebendo mensagens
              </p>
            )}
            {waState === 'error' && errorMsg && (
              <p className="text-xs text-red-600 mt-0.5 break-words">{errorMsg}</p>
            )}
          </div>
          <button
            onClick={() => { setWaState('loading'); fetchStatus() }}
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-white rounded-xl transition-all flex-shrink-0"
            title="Atualizar status"
            disabled={loading}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* QR Code */}
      {waState === 'qr_pending' && qrBase64 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 mb-6 text-center shadow-sm">
          <p className="text-sm font-semibold text-slate-700 mb-1">Escaneie com o WhatsApp</p>
          <p className="text-xs text-slate-400 mb-6">
            WhatsApp → Menu (3 pontos) → Aparelhos Conectados → Conectar aparelho
          </p>
          <div className="flex justify-center mb-6">
            <img
              src={qrBase64}
              alt="QR Code WhatsApp"
              className="w-64 h-64 rounded-2xl border-4 border-slate-100 object-contain"
            />
          </div>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={handleRefreshQR}
              disabled={loading}
              className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Gerar novo QR Code
            </button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3">
        {waState === 'connected' ? (
          <>
            <button
              onClick={handleRefreshQR}
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium px-5 py-3 rounded-xl text-sm transition-all"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <QrCode size={16} />}
              Mostrar QR Code
            </button>
            <button
              onClick={handleDisconnect}
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-white border border-red-200 hover:bg-red-50 text-red-600 font-medium px-5 py-3 rounded-xl text-sm transition-all"
            >
              <Unplug size={16} />
              Desconectar
            </button>
          </>
        ) : (
          <>
            <button
              onClick={handleConnect}
              disabled={loading || waState === 'loading'}
              className="flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-all shadow-sm"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <PlugZap size={16} />}
              {loading ? 'Aguarde...' : waState === 'qr_pending' ? 'Novo QR Code' : 'Conectar WhatsApp'}
            </button>
          </>
        )}
      </div>

      {/* How to connect */}
      {(waState === 'disconnected' || waState === 'qr_pending' || waState === 'error') && (
        <div className="mt-8 bg-slate-50 rounded-2xl border border-slate-100 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-3">Como conectar:</p>
          <ol className="space-y-2 text-sm text-slate-600">
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600 flex-shrink-0 w-5">1.</span>
              Clique em <strong>Conectar WhatsApp</strong>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600 flex-shrink-0 w-5">2.</span>
              Abra o WhatsApp no seu celular
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600 flex-shrink-0 w-5">3.</span>
              Toque em <strong>Menu (3 pontos)</strong> → <strong>Aparelhos Conectados</strong>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600 flex-shrink-0 w-5">4.</span>
              Toque em <strong>Conectar aparelho</strong>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600 flex-shrink-0 w-5">5.</span>
              Aponte a câmera para o QR Code
            </li>
          </ol>
        </div>
      )}

      {/* Nuclear option — only show if error or disconnected */}
      {(waState === 'error' || waState === 'disconnected') && (
        <div className="mt-4">
          <details className="group">
            <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-600 select-none">
              ▸ Opções avançadas (usar somente se travado)
            </summary>
            <div className="mt-3 bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-xs text-red-700 mb-3">
                Se a instância estiver travada ou em estado inconsistente, delete-a e reconecte do zero.
              </p>
              <button
                onClick={handleDeleteInstance}
                disabled={loading}
                className="flex items-center gap-2 text-xs text-red-600 hover:text-red-800 font-medium border border-red-300 bg-white px-3 py-2 rounded-lg transition-all"
              >
                <Trash2 size={13} />
                Deletar instância e reiniciar
              </button>
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
