'use client'
import { useState, useEffect, useRef } from 'react'
import { adminApi } from '@/lib/adminApi'
import {
  Wifi, WifiOff, QrCode, RefreshCw, Loader2,
  CheckCircle2, AlertCircle, Smartphone, PlugZap, Unplug
} from 'lucide-react'

type WaStatus = 'checking' | 'connected' | 'qr_pending' | 'disconnected' | 'error'

export default function WhatsAppPage() {
  const [status, setStatus] = useState<WaStatus>('checking')
  const [connectedPhone, setConnectedPhone] = useState<string | null>(null)
  const [qrBase64, setQrBase64] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [flash, setFlash] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    checkStatus()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  // Auto-poll every 5s while waiting for QR scan
  useEffect(() => {
    if (status === 'qr_pending') {
      pollRef.current = setInterval(checkStatus, 5000)
    } else {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      if (status === 'connected') setQrBase64(null)
    }
  }, [status])

  function showFlash(type: 'ok' | 'err', text: string) {
    setFlash({ type, text })
    setTimeout(() => setFlash(null), 5000)
  }

  async function checkStatus() {
    try {
      const res = await adminApi.whatsappStatus() as Record<string, unknown>
      const state = (res.instance as { state?: string } | undefined)?.state
        ?? (res as { state?: string }).state
      if (state === 'open') {
        setStatus('connected')
        // Try to get phone number from response
        const phone = (res.instance as { owner?: string } | undefined)?.owner
        if (phone) setConnectedPhone(phone)
      } else if ((res as { error?: string }).error === 'instance_not_found') {
        setStatus('disconnected')
      } else {
        setStatus('disconnected')
      }
    } catch {
      setStatus('error')
    }
  }

  async function handleConnect() {
    setLoading(true)
    setFlash(null)
    try {
      const res = await adminApi.whatsappConnect() as Record<string, unknown>
      if ((res as { status?: string }).status === 'already_connected') {
        setStatus('connected')
        showFlash('ok', 'WhatsApp já está conectado!')
        return
      }
      // Instance created, get QR code
      await handleGetQR()
    } catch (e) {
      showFlash('err', `Erro ao conectar: ${e instanceof Error ? e.message : 'Tente novamente'}`)
      setStatus('disconnected')
    } finally {
      setLoading(false)
    }
  }

  async function handleGetQR() {
    setLoading(true)
    try {
      const res = await adminApi.whatsappQRCode() as Record<string, unknown>
      // Evolution API can return base64 in different shapes
      const b64 =
        (res as { base64?: string }).base64 ||
        ((res as { qrcode?: { base64?: string } }).qrcode)?.base64 ||
        (res as { code?: string }).code
      if (b64) {
        setQrBase64(b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`)
        setStatus('qr_pending')
        showFlash('ok', 'Escaneie o QR Code com o WhatsApp do seu celular')
      } else {
        showFlash('err', 'QR Code não disponível. Tente novamente em alguns segundos.')
      }
    } catch (e) {
      showFlash('err', `Erro ao obter QR Code: ${e instanceof Error ? e.message : 'Falha'}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleDisconnect() {
    if (!confirm('Desconectar o WhatsApp? O agente parará de receber mensagens.')) return
    setLoading(true)
    try {
      await adminApi.whatsappDisconnect()
      setStatus('disconnected')
      setConnectedPhone(null)
      setQrBase64(null)
      showFlash('ok', 'WhatsApp desconectado.')
    } catch (e) {
      showFlash('err', e instanceof Error ? e.message : 'Erro ao desconectar')
    } finally {
      setLoading(false)
    }
  }

  const STATUS_CONFIG = {
    checking: { label: 'Verificando...', color: 'text-slate-500', bg: 'bg-slate-50', border: 'border-slate-200', Icon: Loader2 },
    connected: { label: 'Conectado', color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', Icon: Wifi },
    qr_pending: { label: 'Aguardando escaneamento', color: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-200', Icon: QrCode },
    disconnected: { label: 'Desconectado', color: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200', Icon: WifiOff },
    error: { label: 'Erro de conexão', color: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200', Icon: AlertCircle },
  }

  const cfg = STATUS_CONFIG[status]
  const StatusIcon = cfg.Icon

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">WhatsApp</h1>
        <p className="text-slate-500 text-sm mt-0.5">Conecte o número de WhatsApp do agente</p>
      </div>

      {/* Flash message */}
      {flash && (
        <div className={`rounded-xl px-4 py-3 text-sm mb-6 flex items-center gap-2 ${
          flash.type === 'err'
            ? 'bg-red-50 text-red-700 border border-red-200'
            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        }`}>
          {flash.type === 'err' ? <AlertCircle size={15} /> : <CheckCircle2 size={15} />}
          {flash.text}
        </div>
      )}

      {/* Status card */}
      <div className={`rounded-2xl border ${cfg.border} ${cfg.bg} p-6 mb-6`}>
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-white rounded-2xl flex items-center justify-center shadow-sm flex-shrink-0">
            <StatusIcon
              size={26}
              className={`${cfg.color} ${status === 'checking' ? 'animate-spin' : ''}`}
            />
          </div>
          <div className="flex-1">
            <p className={`font-bold text-lg ${cfg.color}`}>{cfg.label}</p>
            {status === 'connected' && connectedPhone && (
              <p className="text-sm text-emerald-600 mt-0.5 flex items-center gap-1.5">
                <Smartphone size={13} />
                {connectedPhone}
              </p>
            )}
            {status === 'qr_pending' && (
              <p className="text-sm text-amber-600 mt-0.5">Verificando automaticamente a cada 5s...</p>
            )}
            {(status === 'disconnected' || status === 'error') && (
              <p className="text-sm text-slate-500 mt-0.5">O agente não está recebendo mensagens</p>
            )}
          </div>
          <button
            onClick={checkStatus}
            className="p-2 text-slate-400 hover:text-slate-700 hover:bg-white rounded-xl transition-all"
            title="Atualizar status"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* QR Code display */}
      {status === 'qr_pending' && qrBase64 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 mb-6 text-center shadow-sm">
          <p className="text-sm font-semibold text-slate-600 mb-1">Escaneie com o WhatsApp</p>
          <p className="text-xs text-slate-400 mb-6">
            Abra o WhatsApp → Aparelhos Conectados → Conectar aparelho
          </p>
          <div className="flex justify-center mb-6">
            <img
              src={qrBase64}
              alt="QR Code WhatsApp"
              className="w-64 h-64 rounded-2xl border-4 border-slate-100"
            />
          </div>
          <button
            onClick={handleGetQR}
            disabled={loading}
            className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1.5 mx-auto transition-colors"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Gerar novo QR Code
          </button>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-col sm:flex-row gap-3">
        {status === 'connected' ? (
          <>
            <button
              onClick={handleGetQR}
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium px-6 py-3 rounded-xl text-sm transition-all"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <QrCode size={16} />}
              Ver QR Code
            </button>
            <button
              onClick={handleDisconnect}
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-red-50 hover:bg-red-100 text-red-600 font-medium px-6 py-3 rounded-xl text-sm transition-all border border-red-200"
            >
              <Unplug size={16} />
              Desconectar
            </button>
          </>
        ) : (
          <>
            <button
              onClick={handleConnect}
              disabled={loading || status === 'checking'}
              className="flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-all shadow-sm"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <PlugZap size={16} />}
              {loading ? 'Conectando...' : 'Conectar WhatsApp'}
            </button>
            {status === 'disconnected' && (
              <button
                onClick={handleGetQR}
                disabled={loading}
                className="flex items-center justify-center gap-2 bg-white hover:bg-slate-50 text-slate-700 font-medium px-6 py-3 rounded-xl text-sm transition-all border border-slate-200"
              >
                <QrCode size={16} />
                Ver QR Code
              </button>
            )}
          </>
        )}
      </div>

      {/* Instructions */}
      <div className="mt-8 bg-slate-50 rounded-2xl border border-slate-100 p-5">
        <p className="text-sm font-semibold text-slate-700 mb-3">Como conectar:</p>
        <ol className="space-y-2 text-sm text-slate-600">
          <li className="flex gap-2"><span className="font-bold text-blue-600 flex-shrink-0">1.</span> Clique em <strong>Conectar WhatsApp</strong></li>
          <li className="flex gap-2"><span className="font-bold text-blue-600 flex-shrink-0">2.</span> Abra o WhatsApp no seu celular</li>
          <li className="flex gap-2"><span className="font-bold text-blue-600 flex-shrink-0">3.</span> Toque em <strong>Aparelhos Conectados</strong> (menu de 3 pontos)</li>
          <li className="flex gap-2"><span className="font-bold text-blue-600 flex-shrink-0">4.</span> Toque em <strong>Conectar aparelho</strong></li>
          <li className="flex gap-2"><span className="font-bold text-blue-600 flex-shrink-0">5.</span> Aponte a câmera para o QR Code acima</li>
        </ol>
      </div>
    </div>
  )
}
