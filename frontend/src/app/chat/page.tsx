'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import AppLayout from '@/components/layout/AppLayout'
import { chat, documents, accounts, ApiError } from '@/lib/api'
import { Send, Paperclip, X, Bot, User, Loader2, Upload } from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'agent'
  content: string
  timestamp: Date
}

interface UploadPreview {
  import_id: string
  bank_name: string | null
  total_found: number
  to_import: number
  duplicates: number
  message: string
}

function formatTime(d: Date) {
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [uploadPreview, setUploadPreview] = useState<UploadPreview | null>(null)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [selectedAccount, setSelectedAccount] = useState<string>('')
  const [accountList, setAccountList] = useState<Array<{ id: string; name: string }>>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Add welcome message
  useEffect(() => {
    setMessages([{
      id: 'welcome',
      role: 'agent',
      content: 'Olá! Eu sou o Rafael, seu assistente financeiro. Como posso te ajudar hoje? 😊\n\nVocê pode me perguntar sobre seu saldo, lançar transações, pedir relatórios ou enviar extratos bancários.',
      timestamp: new Date(),
    }])
    accounts.list().then(data => {
      setAccountList((data as { accounts: Array<{ id: string; name: string }> }).accounts || [])
    }).catch(() => {})
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function addMessage(role: 'user' | 'agent', content: string) {
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role,
      content,
      timestamp: new Date(),
    }])
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    addMessage('user', text)
    setLoading(true)

    try {
      const res = await chat.sendMessage(text, sessionId)
      setSessionId(res.session_id)
      addMessage('agent', res.response)
    } catch (err) {
      addMessage('agent', '❌ Erro ao processar sua mensagem. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''

    setUploadLoading(true)
    addMessage('user', `📎 Enviando arquivo: ${file.name}`)

    try {
      const preview = await documents.upload(file)
      setUploadPreview(preview as UploadPreview)
      addMessage('agent',
        `📊 Analisei o arquivo **${file.name}**!\n\n` +
        `🏦 Banco: ${(preview as UploadPreview).bank_name || 'Não identificado'}\n` +
        `📝 Transações encontradas: ${(preview as UploadPreview).total_found}\n` +
        `✅ Para importar: ${(preview as UploadPreview).to_import}\n` +
        `⚠️ Duplicatas: ${(preview as UploadPreview).duplicates}\n\n` +
        `Confirme abaixo para importar as transações.`
      )
    } catch (err) {
      addMessage('agent', `❌ Erro ao analisar o arquivo: ${err instanceof ApiError ? err.message : 'Tente novamente.'}`)
    } finally {
      setUploadLoading(false)
    }
  }

  async function confirmImport() {
    if (!uploadPreview) return
    setLoading(true)
    try {
      const result = await documents.confirm({
        import_id: uploadPreview.import_id,
        account_id: selectedAccount || undefined,
        skip_duplicates: true,
      })
      addMessage('agent', `✅ ${(result as { message: string }).message || 'Importação concluída!'}`)
      setUploadPreview(null)
    } catch (err) {
      addMessage('agent', `❌ Erro na importação: ${err instanceof ApiError ? err.message : 'Tente novamente.'}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppLayout>
      <div className="flex flex-col h-screen">
        {/* Header */}
        <div className="bg-white border-b border-slate-100 px-6 py-4 flex items-center gap-3 flex-shrink-0">
          <div className="w-10 h-10 bg-blue-600 rounded-full flex items-center justify-center">
            <Bot size={20} className="text-white" />
          </div>
          <div>
            <p className="font-semibold text-slate-800">Rafael Oliveira</p>
            <p className="text-xs text-emerald-500 font-medium">● Online — Assistente Financeiro</p>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 lg:px-6 py-4 space-y-4">
          {messages.map(msg => (
            <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'agent' && (
                <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot size={15} className="text-white" />
                </div>
              )}
              <div className={msg.role === 'agent' ? 'chat-bubble-agent' : 'chat-bubble-user'}>
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                <p className={`text-xs mt-1 ${msg.role === 'user' ? 'text-blue-200' : 'text-slate-400'}`}>
                  {formatTime(msg.timestamp)}
                </p>
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 bg-slate-200 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User size={15} className="text-slate-600" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3 justify-start">
              <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
                <Bot size={15} className="text-white" />
              </div>
              <div className="chat-bubble-agent">
                <div className="flex gap-1 items-center py-1">
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Upload preview card */}
        {uploadPreview && (
          <div className="mx-4 lg:mx-6 mb-3 bg-blue-50 border border-blue-200 rounded-2xl p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-blue-800">Confirmar importação</p>
              <button onClick={() => setUploadPreview(null)} className="text-slate-400 hover:text-slate-600">
                <X size={16} />
              </button>
            </div>
            {accountList.length > 0 && (
              <div className="mb-3">
                <label className="block text-xs text-slate-600 mb-1">Conta de destino (opcional)</label>
                <select
                  value={selectedAccount}
                  onChange={e => setSelectedAccount(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
                >
                  <option value="">Sem conta específica</option>
                  {accountList.map(a => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="flex gap-2">
              <button
                onClick={confirmImport}
                disabled={loading}
                className="flex-1 bg-blue-600 text-white text-sm font-medium py-2 rounded-xl hover:bg-blue-700 disabled:opacity-50 transition-all"
              >
                {loading ? 'Importando...' : `✅ Importar ${uploadPreview.to_import} transações`}
              </button>
              <button
                onClick={() => setUploadPreview(null)}
                className="px-4 py-2 text-sm text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-100 transition-all"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="bg-white border-t border-slate-100 px-4 lg:px-6 py-4 flex-shrink-0">
          <div className="flex items-end gap-3 max-w-4xl mx-auto">
            {/* File upload */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,image/*"
              className="hidden"
              onChange={handleFileUpload}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadLoading}
              title="Enviar extrato (PDF ou foto)"
              className="w-10 h-10 flex items-center justify-center text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-xl transition-all flex-shrink-0 disabled:opacity-50"
            >
              {uploadLoading ? <Loader2 size={18} className="animate-spin" /> : <Paperclip size={18} />}
            </button>

            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Digite uma mensagem... (Enter para enviar)"
              rows={1}
              className="flex-1 resize-none border border-slate-200 rounded-2xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent max-h-32 overflow-y-auto"
              style={{ lineHeight: '1.5' }}
            />

            <button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              className="w-10 h-10 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl flex items-center justify-center transition-all flex-shrink-0"
            >
              <Send size={16} />
            </button>
          </div>
          <p className="text-center text-xs text-slate-400 mt-2">
            Shift+Enter para nova linha • Arraste um PDF ou foto para enviar extrato
          </p>
        </div>
      </div>
    </AppLayout>
  )
}
