'use client'
import { useEffect, useState } from 'react'
import AppLayout from '@/components/layout/AppLayout'
import { profile as profileApi, accounts, ApiError } from '@/lib/api'
import { Save, PlusCircle, User, CreditCard, Smartphone, Lock } from 'lucide-react'

export default function SettingsPage() {
  const [userData, setUserData] = useState<Record<string, unknown>>({})
  const [accountList, setAccountList] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [form, setForm] = useState({ name: '', business_name: '', whatsapp_number: '', telegram_chat_id: '' })
  const [pwForm, setPwForm] = useState({ current: '', newPw: '' })
  const [acctForm, setAcctForm] = useState({ name: '', type: 'checking', bank_name: '', initial_balance: '' })
  const [tab, setTab] = useState<'profile' | 'accounts' | 'channels'>('profile')

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [prof, accts] = await Promise.all([profileApi.get(), accounts.list()])
        setUserData(prof)
        setForm({
          name: (prof.name as string) || '',
          business_name: (prof.business_name as string) || '',
          whatsapp_number: (prof.whatsapp_number as string) || '',
          telegram_chat_id: (prof.telegram_chat_id as string) || '',
        })
        setAccountList((accts as { accounts: Array<Record<string, unknown>> }).accounts || [])
      } catch (e) { console.error(e) }
      finally { setLoading(false) }
    }
    load()
  }, [])

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    try {
      await profileApi.update(form)
      // Update stored name
      localStorage.setItem('finagent_name', form.name)
      setMsg({ type: 'ok', text: 'Perfil atualizado!' })
    } catch (err) {
      setMsg({ type: 'err', text: err instanceof ApiError ? err.message : 'Erro ao salvar' })
    } finally { setSaving(false) }
  }

  async function createAccount(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await accounts.create({ ...acctForm, initial_balance: parseFloat(acctForm.initial_balance) || 0 })
      setAcctForm({ name: '', type: 'checking', bank_name: '', initial_balance: '' })
      const accts = await accounts.list()
      setAccountList((accts as { accounts: Array<Record<string, unknown>> }).accounts || [])
      setMsg({ type: 'ok', text: 'Conta criada!' })
    } catch (err) {
      setMsg({ type: 'err', text: err instanceof ApiError ? err.message : 'Erro ao criar conta' })
    } finally { setSaving(false) }
  }

  const TABS = [
    { id: 'profile' as const, label: 'Perfil', icon: User },
    { id: 'accounts' as const, label: 'Contas Bancárias', icon: CreditCard },
    { id: 'channels' as const, label: 'Canais', icon: Smartphone },
  ]

  return (
    <AppLayout>
      <div className="p-6 lg:p-8 max-w-3xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-800">Configurações</h1>
          <p className="text-slate-500 text-sm mt-0.5">Gerencie sua conta e preferências</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit mb-6">
          {TABS.map(t => {
            const Icon = t.icon
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  tab === t.id ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                }`}>
                <Icon size={14} />{t.label}
              </button>
            )
          })}
        </div>

        {msg && (
          <div className={`rounded-xl px-4 py-3 text-sm mb-4 ${msg.type === 'ok' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {msg.text}
          </div>
        )}

        {loading ? (
          <div className="bg-white rounded-2xl border border-slate-100 p-12 text-center text-slate-400 text-sm">Carregando...</div>
        ) : (
          <>
            {/* Profile tab */}
            {tab === 'profile' && (
              <div className="bg-white rounded-2xl border border-slate-100 p-6">
                <h2 className="font-semibold text-slate-800 mb-5">Informações Pessoais</h2>
                <form onSubmit={saveProfile} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Nome completo</label>
                    <input type="text" required value={form.name}
                      onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Nome da empresa (opcional)</label>
                    <input type="text" value={form.business_name}
                      onChange={e => setForm(p => ({ ...p, business_name: e.target.value }))}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">E-mail (não editável)</label>
                    <input type="email" value={(userData.email as string) || ''} disabled
                      className="w-full border border-slate-100 rounded-lg px-3 py-2.5 text-sm bg-slate-50 text-slate-400" />
                  </div>
                  <button type="submit" disabled={saving}
                    className="flex items-center gap-2 bg-blue-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-all">
                    <Save size={15} />
                    {saving ? 'Salvando...' : 'Salvar Perfil'}
                  </button>
                </form>
              </div>
            )}

            {/* Accounts tab */}
            {tab === 'accounts' && (
              <div className="space-y-4">
                {/* Existing accounts */}
                {accountList.map(acct => (
                  <div key={acct.id as string} className="bg-white rounded-2xl border border-slate-100 p-5 flex items-center gap-4">
                    <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center flex-shrink-0">
                      <CreditCard size={18} className="text-blue-600" />
                    </div>
                    <div className="flex-1">
                      <p className="font-medium text-slate-800">{acct.name as string}</p>
                      <p className="text-sm text-slate-500">{acct.bank_name as string || acct.type as string}</p>
                    </div>
                    <p className="font-semibold text-slate-700">
                      {(acct.current_balance as number || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                    </p>
                  </div>
                ))}

                {/* Add new account */}
                <div className="bg-white rounded-2xl border border-slate-100 p-6">
                  <h2 className="font-semibold text-slate-800 mb-4 flex items-center gap-2">
                    <PlusCircle size={18} className="text-blue-600" />
                    Adicionar Conta
                  </h2>
                  <form onSubmit={createAccount} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Nome da conta</label>
                      <input type="text" required value={acctForm.name}
                        onChange={e => setAcctForm(p => ({ ...p, name: e.target.value }))}
                        placeholder="Nubank, Bradesco Corrente..."
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Banco</label>
                      <input type="text" value={acctForm.bank_name}
                        onChange={e => setAcctForm(p => ({ ...p, bank_name: e.target.value }))}
                        placeholder="Nubank, Itaú..."
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Tipo</label>
                      <select value={acctForm.type} onChange={e => setAcctForm(p => ({ ...p, type: e.target.value }))}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                        <option value="checking">Conta Corrente</option>
                        <option value="savings">Poupança</option>
                        <option value="credit">Cartão de Crédito</option>
                        <option value="investment">Investimento</option>
                        <option value="cash">Dinheiro em Espécie</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Saldo inicial (R$)</label>
                      <input type="number" step="0.01" value={acctForm.initial_balance}
                        onChange={e => setAcctForm(p => ({ ...p, initial_balance: e.target.value }))}
                        placeholder="0,00"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                    </div>
                    <div className="sm:col-span-2">
                      <button type="submit" disabled={saving}
                        className="flex items-center gap-2 bg-blue-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-all">
                        <PlusCircle size={15} />
                        {saving ? 'Criando...' : 'Adicionar Conta'}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {/* Channels tab */}
            {tab === 'channels' && (
              <div className="bg-white rounded-2xl border border-slate-100 p-6">
                <h2 className="font-semibold text-slate-800 mb-2">Canais de Comunicação</h2>
                <p className="text-sm text-slate-500 mb-5">
                  Configure seus canais para receber mensagens do agente e alertas.
                </p>
                <form onSubmit={saveProfile} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1 flex items-center gap-1.5">
                      <span className="text-emerald-600">📱</span> WhatsApp
                    </label>
                    <input type="tel" value={form.whatsapp_number}
                      onChange={e => setForm(p => ({ ...p, whatsapp_number: e.target.value }))}
                      placeholder="5511999999999 (com DDI)"
                      className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                    <p className="text-xs text-slate-400 mt-1">
                      Formato: 55 + DDD + número (ex: 5511999999999)
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1 flex items-center gap-1.5">
                      <span className="text-blue-500">✈️</span> Telegram Chat ID
                    </label>
                    <input type="text" value={form.telegram_chat_id}
                      onChange={e => setForm(p => ({ ...p, telegram_chat_id: e.target.value }))}
                      placeholder="123456789"
                      className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
                    <p className="text-xs text-slate-400 mt-1">
                      Envie /start para o bot e ele mostrará seu Chat ID
                    </p>
                  </div>
                  <button type="submit" disabled={saving}
                    className="flex items-center gap-2 bg-blue-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-all">
                    <Save size={15} />
                    {saving ? 'Salvando...' : 'Salvar Canais'}
                  </button>
                </form>
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  )
}
