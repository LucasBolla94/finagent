'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { adminApi, getAdminKey } from '@/lib/adminApi'
import { ChevronLeft, Wifi, WifiOff, QrCode, RefreshCw, Loader2, CheckCircle2 } from 'lucide-react'

type Status = 'checking' | 'connected' | 'disconnected' | 'error'

export default function WhatsAppPage() {
  const router = useRouter()
  const [status, setStatus] = useState<Status>('checking')
  const [statusDetail, setStatusDetail] = useState<Record<string, unknown>>({})
  const [qrData, setQrData] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [pollInterval, setPollInterval] = useState<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (!getAdminKey()) { router.push('/admin'); return }
    checkStatus()
  }, [])

  // Auto-refresh status every 5s when showing QR code
  useEffect(() => {
    if (qrData && !pollInterval) {
      const interval = setInterval(checkStatus, 5000)
      setPollInterval(interval)
    }
    if (!qrData && pollInterval) {
      clearInterval(pollInterval)
      setPollInterval(null)
    }
    return () => { if (pollInterval) clearInterval(pollInterval) }
  }, [qrData])

  async function checkStatus() {
    try {
      const res = await adminApi.whatsappStatus()
      setStatusDetail(res)
      const state = (res as { instance?: { state?: string } }).instance?.state
      if (state === 'open') {
        setStatus('connected')
        setQrData(null)
      } else if (state === 'connecting' || state === 'close') {
        setStatus('disconnected')
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
    setMessage('')
    try {
      const res = await adminApi.whatsappConnect()
      if ((res as { status?: string }).status === 'already_connected') {
        setStatus('connected')
        setMessage('✅ WhatsApp já está conectado!')
      } else {
        setMessage('Instance criada! Obtendo QR Code...')
        await loadQRCode()
      }
    } catch (e) {
      setMessage(`❌ Erro: ${e instanceof Error ? e.message : 'Falha na conexão'}`)
    } finally {
      setLoading(false)
    }
  }

  async function loadQRCode() {
    setLoading(true)
    try {
      const res = await adminApi.whatsappQRCode()
      const base64 = (res as { base64?: string }).base64 || (res as { qrcode?: { base64?: string } }).qrcode?.base64
      const code = (res as { code?: string }).code || (res as { qrcode?: { code?: string } }).qrcode?.code
      if (base64) {
        setQrData(`data:image/png;base64,${base64.replace(/^data:image\/\w+;base64,/, '')}`)
      } else if (code) {
        setQrData(code)
      } else {
        setMessage('⚠️ QR code não disponível. Verifique o Evolution API.')
      }
    } catch (e) {
      setMessage(`❌ Erro ao obter QR code: ${e instanceof Error ? e.message : 'Tente novamente'}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleDisconnect() {
    if (!confirm('Desconectar o WhatsApp? Os clientes não receberão mais mensagens até reconectar.')) return
    setLoading(true)
    try {
      await adminApi.whatsappDisconnect()
      setStatus('disconnected')
      setQrData(null)
      setMessage('WhatsApp desconectado.')
    } catch (e) {
      setMessage(`❌ Erro: ${e instanceof Error ? e.message : 'Falha'}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b border-slate-100 px-6 py-4">
        <Link href="/admin" className="flex items-center gap-2 text-slate-600 hover:text-slate-800 text-sm mb-1 w-fit">
          <ChevronLeft size={16} />Voltar
        </Link>
        <h1 className="text-xl font-bold text-slate-800">WhatsApp Business</h1>
      </div>

      <div className="p-6 max-w-lg mx-auto">
        {/* Status card */}
        <div className={`rounded-2xl p-6 mb-6 border ${
          status === 'connected' ? 'bg-emerald-50 border-emerald-100' :
          status === 'checking' ? 'bg-slate-50 border-slate-100' :
          'bg-amber-50 border-amber-100'
        }`}>
          <div className="flex items-center gap-3">
            {status === 'checking' ? (
              <Loader2 size={24} className="text-slate-400 animate-spin" />
            ) : status === 'connected' ? (
              <CheckCircle2 size={24} className="text-emerald-600" />
            ) : (
              <WifiOff size={24} className="text-amber-500" />
            )}
            <div>
              <p className={`font-semibold ${
                status === 'connected' ? 'text-emerald-700' :
                status === 'checking' ? 'text-slate-600' :
                'text-amber-700'
              }`}>
                {{
                  connected: '✅ Conectado',
                  disconnected: '⚠️ Desconectado',
                  checking: 'Verificando...',
                  error: '❌ Erro de conexão',
                }[status]}
              </p>
              {status === 'connected' && (
                <p className="text-sm text-emerald-600">WhatsApp pronto para receber mensagens</p>
              )}
              {status === 'disconnected' && (
                <p className="text-sm text-amber-600">Escaneie o QR Code para conectar</p>
              )}
            </div>
            <button onClick={checkStatus} className="ml-auto text-slate-400 hover:text-slate-600 transition-colors p-1">
              <RefreshCw size={16} />
            </button>
          </div>
        </div>

        {message && (
          <div className={`rounded-xl px-4 py-3 text-sm mb-4 ${message.startsWith('❌') ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-blue-50 text-blue-700 border border-blue-200'}`}>
            {message}
          </div>
        )}

        {/* QR Code display */}
        {qrData && (
          <div className="bg-white rounded-2xl border border-slate-100 p-6 mb-6 text-center">
            <p className="font-semibold text-slate-800 mb-1">Escaneie com o WhatsApp</p>
            <p className="text-sm text-slate-500 mb-4">
              Abra o WhatsApp → Menu → Aparelhos conectados → Conectar aparelho
            </p>
            {qrData.startsWith('data:') ? (
              <img src={qrData} alt="QR Code" className="mx-auto max-w-xs rounded-xl" />
            ) : (
              <div className="bg-slate-100 rounded-xl p-4 font-mono text-xs text-slate-600 text-left break-all">
                {qrData}
              </div>
            )}
            <p className="text-xs text-slate-400 mt-3 flex items-center justify-center gap-1">
              <Loader2 size={12} className="animate-spin" />
              Verificando conexão automaticamente...
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="space-y-3">
          {status !== 'connected' && (
            <button
              onClick={qrData ? loadQRCode : handleConnect}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-medium py-3 rounded-xl transition-all"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <QrCode size={18} />}
              {loading ? 'Aguarde...' : qrData ? 'Atualizar QR Code' : 'Conectar WhatsApp'}
            </button>
          )}

          {status === 'connected' && (
            <button
              onClick={handleDisconnect}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-red-50 hover:bg-red-100 disabled:opacity-50 text-red-600 font-medium py-3 rounded-xl transition-all border border-red-200"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <WifiOff size={18} />}
              Desconectar
            </button>
          )}
        </div>

        {/* Instructions */}
        <div className="bg-blue-50 rounded-2xl p-5 mt-6 border border-blue-100">
          <p className="text-sm font-semibold text-blue-800 mb-2">📋 Como conectar</p>
          <ol className="text-sm text-blue-700 space-y-1 list-decimal list-inside">
            <li>Clique em "Conectar WhatsApp"</li>
            <li>Aparecerá um QR Code</li>
            <li>Abra o WhatsApp no celular</li>
            <li>Vá em Menu → Aparelhos Conectados</li>
            <li>Escaneie o QR Code</li>
            <li>Pronto! O agente estará online</li>
          </ol>
        </div>
      </div>
    </div>
  )
}
