import { useEffect, useState, type FormEvent } from 'react'
import { Badge, Button, Card, CardTitle, Field, Input, Select } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { api, apiUpload, errorMessage } from '../../lib/api'
import type { ImportOutcome } from '../../types'

interface PortalClass { id: string; name: string }

export function ImportPage() {
  const { notify } = useToast()
  const [classes, setClasses] = useState<PortalClass[]>([])
  const [classId, setClassId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ImportOutcome | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void api<PortalClass[]>('/portal/teacher/classes').then((rows) => {
      setClasses(rows)
      if (rows.length > 0) setClassId(rows[0].id)
    }).catch(() => setClasses([]))
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!classId || !file) {
      notify('Pilih kelas dan berkas CSV/XLSX.', 'error')
      return
    }
    setBusy(true)
    try {
      const outcome = await apiUpload<ImportOutcome>(`/learning/import-students?class_id=${encodeURIComponent(classId)}`, file)
      setResult(outcome)
      notify(`Import selesai: ${outcome.created} dibuat, ${outcome.updated} ditambahkan ke kelas, ${outcome.skipped} dilewati.`)
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Impor siswa</h1>
        <p className="mt-1 text-sm text-slate-500">Kolom wajib: username, full_name, password. Opsional: email, student_number.</p>
      </div>

      <Card>
        <CardTitle title="Berkas siswa" subtitle="CSV UTF-8 atau XLSX, maksimal 5 MB. Username yang sudah ada tidak ditimpa." />
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(event) => void submit(event)}>
          <Field label="Kelas tujuan">
            <Select value={classId} onChange={(event) => setClassId(event.target.value)}>
              <option value="">Pilih kelas</option>
              {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
            </Select>
          </Field>
          <Field label="Berkas">
            <Input type="file" accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </Field>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={busy}>{busy ? 'Mengimpor…' : 'Impor siswa'}</Button>
          </div>
        </form>
      </Card>

      {result && (
        <Card>
          <CardTitle title="Hasil impor" />
          <div className="flex flex-wrap gap-2">
            <Badge tone="green">Dibuat: {result.created}</Badge>
            <Badge tone="indigo">Ditambahkan: {result.updated}</Badge>
            <Badge tone="amber">Dilewati: {result.skipped}</Badge>
          </div>
          {result.errors.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-rose-700">
              {result.errors.map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}
            </ul>
          )}
        </Card>
      )}
    </div>
  )
}
