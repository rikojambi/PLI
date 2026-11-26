import { useEffect, useState } from 'react'
import { Badge, Button, Card, CardTitle, Checkbox, Field, Input, Spinner } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { api, errorMessage } from '../../lib/api'
import type { BktParams, BktParamsInfo } from '../../types'

const fields: Array<{ key: keyof BktParams; label: string; hint: string }> = [
  { key: 'p_init', label: 'Probabilitas awal (p_init)', hint: 'Penguasaan sebelum ada jawaban.' },
  { key: 'p_transit', label: 'Peluang belajar (p_transit)', hint: 'Peluang menguasai setelah satu kesempatan.' },
  { key: 'p_slip', label: 'Peluang salah (p_slip)', hint: 'Salah menjawab meski sudah menguasai.' },
  { key: 'p_guess', label: 'Peluang menebak (p_guess)', hint: 'Benar hanya karena menebak.' },
  { key: 'mastery_threshold', label: 'Ambang penguasaan', hint: 'Batas status “mastered”.' },
]

export function EngineSettingsPage() {
  const { notify } = useToast()
  const [info, setInfo] = useState<BktParamsInfo | null>(null)
  const [draft, setDraft] = useState<BktParams | null>(null)
  const [recompute, setRecompute] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void api<BktParamsInfo>('/intelligence/bkt-params')
      .then((value) => { setInfo(value); setDraft({ ...value.params }); setError('') })
      .catch((err) => setError(errorMessage(err)))
  }, [])

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      const result = await api<{ params: BktParams; recomputed_students: number }>('/intelligence/bkt-params', {
        method: 'PUT',
        body: { ...draft, recompute },
      })
      setInfo((current) => current ? { ...current, params: result.params, source: 'database_override' } : current)
      setDraft({ ...result.params })
      notify(`Parameter disimpan. ${result.recomputed_students} profil siswa dihitung ulang.`)
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Pengaturan mesin intelijen</h1>
        <p className="mt-1 text-sm text-slate-500">
          Parameter disimpan di server dan dapat diubah administrator. Setiap perubahan tercatat di log audit.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {!info || !draft ? <Spinner label="Memuat parameter…" /> : (
        <>
          <Card>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <CardTitle title="Parameter Bayesian Knowledge Tracing" subtitle="Nilai harus antara 0 dan 1; p_slip + p_guess harus kurang dari 1." />
              <Badge tone={info.source === 'database_override' ? 'green' : 'slate'}>
                {info.source === 'database_override' ? 'Override sekolah' : 'Default lingkungan'}
              </Badge>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {fields.map((item) => (
                <Field key={item.key} label={item.label} hint={item.hint}>
                  <Input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={draft[item.key]}
                    onChange={(event) => setDraft({ ...draft, [item.key]: Number(event.target.value) })}
                  />
                </Field>
              ))}
            </div>
            <div className="mt-4">
              <Checkbox
                label="Hitung ulang semua profil siswa setelah menyimpan"
                checked={recompute}
                onChange={(event) => setRecompute(event.target.checked)}
              />
            </div>
            <div className="mt-5 flex justify-end">
              <Button onClick={() => void save()} disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan parameter'}</Button>
            </div>
          </Card>

          <Card>
            <CardTitle title="Arti parameter" subtitle="Definisi dari server agar tidak ada perbedaan interpretasi." />
            <dl className="mt-3 space-y-2 text-sm">
              {Object.entries(info.definitions).map(([key, value]) => (
                <div key={key} className="flex gap-3">
                  <dt className="w-40 shrink-0 font-mono text-xs text-slate-500">{key}</dt>
                  <dd className="text-slate-600">{value}</dd>
                </div>
              ))}
            </dl>
            {info.updated_at && <p className="mt-4 text-xs text-slate-400">Terakhir diubah: {info.updated_at}</p>}
          </Card>
        </>
      )}
    </div>
  )
}
