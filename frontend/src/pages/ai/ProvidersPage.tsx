import { useEffect, useState } from 'react'
import { useToast } from '../../components/Toast'
import { Badge, Button, Card, CardTitle, Checkbox, EmptyState, Field, Input, Modal, Spinner } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import type { AiAdapterInfo, AiBudget, AiBudgetStatus, AiModel, AiProvider } from '../../types'

interface ProviderForm {
  display_name: string
  base_url: string
  model: string
  embedding_model: string
  api_key_env: string
  input_cost_per_million: number
  output_cost_per_million: number
  max_tokens: number
  priority: number
  is_active: boolean
  is_primary: boolean
  is_fallback: boolean
}

function formFrom(provider: AiProvider): ProviderForm {
  return {
    display_name: provider.display_name,
    base_url: provider.base_url ?? '',
    model: provider.model ?? '',
    embedding_model: provider.embedding_model ?? '',
    api_key_env: provider.api_key_env ?? '',
    input_cost_per_million: provider.input_cost_per_million,
    output_cost_per_million: provider.output_cost_per_million,
    max_tokens: provider.max_tokens,
    priority: provider.priority,
    is_active: provider.is_active,
    is_primary: provider.is_primary,
    is_fallback: provider.is_fallback,
  }
}

export function ProvidersPage() {
  const { notify } = useToast()
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [adapters, setAdapters] = useState<AiAdapterInfo[]>([])
  const [budget, setBudget] = useState<AiBudgetStatus | null>(null)
  const [budgetDraft, setBudgetDraft] = useState<AiBudget | null>(null)
  const [models, setModels] = useState<Record<string, AiModel[]>>({})
  const [editing, setEditing] = useState<AiProvider | null>(null)
  const [form, setForm] = useState<ProviderForm | null>(null)
  const [newModel, setNewModel] = useState<AiProvider | null>(null)
  const [modelId, setModelId] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = () => {
    Promise.all([
      api<AiProvider[]>('/ai/providers'),
      api<{ adapters: AiAdapterInfo[] }>('/ai/catalog'),
      api<AiBudgetStatus>('/ai/budget'),
    ])
      .then(([list, catalog, status]) => {
        setProviders(list)
        setAdapters(catalog.adapters)
        setBudget(status)
        setBudgetDraft({ ...status.policy })
        setError('')
        return Promise.all(list.map(async (provider) => {
          const rows = await api<AiModel[]>(`/ai/providers/${provider.id}/models`)
          return [provider.id, rows] as const
        }))
      })
      .then((pairs) => setModels(Object.fromEntries(pairs)))
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const run = async (key: string, task: () => Promise<void>) => {
    setBusy(key)
    try {
      await task()
      load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy('')
    }
  }

  const saveProvider = async () => {
    if (!editing || !form) return
    await run(`save-${editing.id}`, async () => {
      const result = await api<AiProvider>(`/ai/providers/${editing.id}`, {
        method: 'PATCH', body: form,
      })
      notify(`Penyedia ${result.display_name} diperbarui`)
      setEditing(null)
      setForm(null)
    })
  }

  const saveBudget = async () => {
    if (!budgetDraft) return
    await run('budget', async () => {
      await api('/ai/budget', { method: 'PUT', body: budgetDraft })
      notify('Kebijakan anggaran AI disimpan')
    })
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Penyedia AI</h1>
        <p className="mt-1 text-sm text-slate-500">
          Kunci API hanya berupa referensi environment variable di server. ID model tidak pernah diasumsikan: model
          harus ditemukan dari API penyedia atau diverifikasi administrator.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {loading ? <Spinner label="Memuat penyedia AI…" /> : (
        <>
          <Card>
            <CardTitle title="Status anggaran" subtitle="Pemakaian dihitung dari catatan penggunaan nyata pada server." />
            {budget && budgetDraft && (
              <>
                <div className="grid gap-3 sm:grid-cols-4">
                  <div><p className="text-xs text-slate-500">Token 24 jam</p><p className="font-semibold">{budget.used_today_tokens} / {budget.policy.daily_token_limit}</p></div>
                  <div><p className="text-xs text-slate-500">Sisa token</p><p className="font-semibold">{budget.daily_remaining_tokens}</p></div>
                  <div><p className="text-xs text-slate-500">Biaya 30 hari</p><p className="font-semibold">${budget.used_30d_cost_usd}</p></div>
                  <div><p className="text-xs text-slate-500">Sisa biaya</p><p className="font-semibold">${budget.cost_remaining_usd}</p></div>
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-4">
                  <Field label="Batas token harian"><Input type="number" min={0} value={budgetDraft.daily_token_limit} onChange={(e) => setBudgetDraft({ ...budgetDraft, daily_token_limit: Number(e.target.value) })} /></Field>
                  <Field label="Batas biaya 30 hari (USD)"><Input type="number" min={0} step="0.01" value={budgetDraft.monthly_cost_limit_usd} onChange={(e) => setBudgetDraft({ ...budgetDraft, monthly_cost_limit_usd: Number(e.target.value) })} /></Field>
                  <Field label="Maks token/permintaan"><Input type="number" min={64} value={budgetDraft.max_tokens_per_request} onChange={(e) => setBudgetDraft({ ...budgetDraft, max_tokens_per_request: Number(e.target.value) })} /></Field>
                  <Field label="Izinkan biaya unknown"><Checkbox label="Izinkan" checked={budgetDraft.allow_unknown_cost} onChange={(e) => setBudgetDraft({ ...budgetDraft, allow_unknown_cost: e.target.checked })} /></Field>
                </div>
                <div className="mt-4 flex justify-end"><Button onClick={() => void saveBudget()} disabled={busy === 'budget'}>{busy === 'budget' ? 'Menyimpan…' : 'Simpan anggaran'}</Button></div>
              </>
            )}
          </Card>

          <Card>
            <CardTitle title="Panduan adapter" subtitle="Base URL bawaan boleh diubah; tidak ada model yang dibundling." />
            <div className="grid gap-3 sm:grid-cols-2">
              {adapters.map((item) => (
                <div key={item.name} className="rounded-xl bg-slate-50 p-3 text-xs">
                  <div className="flex items-center justify-between gap-2"><span className="font-semibold text-slate-800">{item.label}</span><Badge tone={item.requires_key ? 'amber' : 'green'}>{item.requires_key ? 'Perlu kunci' : 'Lokal'}</Badge></div>
                  <p className="mt-1 text-slate-500">{item.note}</p>
                  <p className="mt-1 font-mono text-[11px] text-slate-400">{item.discovery}</p>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardTitle title="Daftar penyedia" subtitle="Uji koneksi setelah model terverifikasi. Status kegagalan ditampilkan apa adanya." />
            {providers.length === 0 ? <EmptyState message="Belum ada penyedia. Jalankan seed atau hubungi administrator." /> : (
              <div className="space-y-4">
                {providers.map((provider) => {
                  const rows = models[provider.id] ?? []
                  return (
                    <div key={provider.id} className="rounded-xl border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-semibold">{provider.display_name}</p>
                            <Badge tone={provider.is_active ? 'green' : 'slate'}>{provider.is_active ? 'Aktif' : 'Nonaktif'}</Badge>
                            {provider.is_primary && <Badge tone="indigo">Utama</Badge>}
                            {provider.is_fallback && <Badge tone="amber">Cadangan</Badge>}
                          </div>
                          <p className="mt-1 text-xs text-slate-500">{provider.adapter} · {provider.base_url || '(base URL belum diisi)'}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            Kunci: {provider.has_key ? <span className="font-mono">{provider.key_hint ?? 'terkonfigurasi'}</span> : 'belum tersedia di server'}
                          </p>
                          {provider.last_error && <p className="mt-1 text-xs text-rose-600">Error terakhir: {provider.last_error}</p>}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button variant="secondary" onClick={() => { setEditing(provider); setForm(formFrom(provider)) }}>Ubah</Button>
                          <Button variant="secondary" disabled={busy === `discover-${provider.id}`} onClick={() => void run(`discover-${provider.id}`, async () => {
                            const found = await api<AiModel[]>(`/ai/providers/${provider.id}/discover`, { method: 'POST' })
                            notify(`${found.length} model ditemukan`)
                          })}>{busy === `discover-${provider.id}` ? 'Mencari…' : 'Temukan model'}</Button>
                          <Button variant="secondary" onClick={() => { setNewModel(provider); setModelId('') }}>Tambah model</Button>
                          <Button disabled={busy === `test-${provider.id}`} onClick={() => void run(`test-${provider.id}`, async () => {
                            const result = await api<{ ok: boolean; detail: string }>(`/ai/providers/${provider.id}/test`, { method: 'POST' })
                            notify(result.detail, result.ok ? 'success' : 'error')
                          })}>{busy === `test-${provider.id}` ? 'Menguji…' : 'Uji'}</Button>
                        </div>
                      </div>
                      <div className="mt-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Model terverifikasi ({rows.length})</p>
                        {rows.length === 0 ? <p className="mt-1 text-xs text-slate-500">Belum ada model. Penyedia ini belum dapat dipakai.</p> : (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {rows.map((model) => (
                              <button
                                key={model.id}
                                type="button"
                                onClick={() => void run(`model-${model.id}`, async () => {
                                  await api(`/ai/models/${model.id}`, { method: 'PATCH', body: { is_enabled: !model.is_enabled } })
                                  notify(model.is_enabled ? 'Model dinonaktifkan' : 'Model diaktifkan')
                                })}
                                className={`rounded-full border px-3 py-1 text-xs font-medium ${model.is_enabled ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-slate-200 bg-slate-50 text-slate-500'}`}
                              >
                                {model.model_id} · {model.is_enabled ? 'aktif' : 'nonaktif'}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        </>
      )}

      {editing && form && (
        <Modal title={`Ubah ${editing.display_name}`} onClose={() => { setEditing(null); setForm(null) }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nama tampilan"><Input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></Field>
            <Field label="Base URL"><Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} /></Field>
            <Field label="Model chat" hint="Kosongkan untuk memilih otomatis dari model terverifikasi."><Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} /></Field>
            <Field label="Model embedding"><Input value={form.embedding_model} onChange={(e) => setForm({ ...form, embedding_model: e.target.value })} /></Field>
            <Field label="Env var kunci API" hint="Hanya nama variable, bukan nilai kunci."><Input value={form.api_key_env} onChange={(e) => setForm({ ...form, api_key_env: e.target.value })} /></Field>
            <Field label="Prioritas"><Input type="number" min={1} value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} /></Field>
            <Field label="Maks token"><Input type="number" min={64} value={form.max_tokens} onChange={(e) => setForm({ ...form, max_tokens: Number(e.target.value) })} /></Field>
            <Field label="Harga input / 1M token"><Input type="number" min={0} step="0.01" value={form.input_cost_per_million} onChange={(e) => setForm({ ...form, input_cost_per_million: Number(e.target.value) })} /></Field>
            <Field label="Harga output / 1M token"><Input type="number" min={0} step="0.01" value={form.output_cost_per_million} onChange={(e) => setForm({ ...form, output_cost_per_million: Number(e.target.value) })} /></Field>
            <div className="space-y-1">
              <Checkbox label="Aktif" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
              <Checkbox label="Penyedia utama" checked={form.is_primary} onChange={(e) => setForm({ ...form, is_primary: e.target.checked })} />
              <Checkbox label="Penyedia cadangan" checked={form.is_fallback} onChange={(e) => setForm({ ...form, is_fallback: e.target.checked })} />
            </div>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => { setEditing(null); setForm(null) }}>Batal</Button>
            <Button onClick={() => void saveProvider()} disabled={busy.startsWith('save-')}>Simpan</Button>
          </div>
        </Modal>
      )}

      {newModel && (
        <Modal title={`Verifikasi model pada ${newModel.display_name}`} onClose={() => setNewModel(null)}>
          <Field label="ID model" hint="Salin dari daftar resmi penyedia atau hasil discovery; tidak ditebak."><Input value={modelId} onChange={(e) => setModelId(e.target.value)} /></Field>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setNewModel(null)}>Batal</Button>
            <Button disabled={modelId.trim().length < 2 || busy === 'add-model'} onClick={() => void run('add-model', async () => {
              await api(`/ai/providers/${newModel.id}/models`, { method: 'POST', body: { model_id: modelId.trim() } })
              notify('Model diverifikasi dan ditambahkan')
              setNewModel(null)
            })}>{busy === 'add-model' ? 'Menyimpan…' : 'Tambahkan'}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
