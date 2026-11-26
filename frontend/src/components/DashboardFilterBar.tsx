import { useEffect, useState } from 'react'
import { api, errorMessage } from '../lib/api'
import { useToast } from './Toast'
import { Button, Field, Select, Input } from './ui'

export interface FilterOption {
  id: string
  name: string
  code?: string
  subject_id?: string
}

export interface PeriodOption {
  value: string
  label: string
}

export interface DashboardFilterOptions {
  classes: FilterOption[]
  subjects: FilterOption[]
  competencies: FilterOption[]
  students: FilterOption[]
  periods: PeriodOption[]
  scope: 'self' | 'admin' | 'teacher'
}

export interface DashboardFilterState {
  period: string
  class_id: string
  subject_id: string
  competency_id: string
  student_id: string
  date_from: string
  date_to: string
}

export const DEFAULT_FILTERS: DashboardFilterState = {
  period: '30d',
  class_id: '',
  subject_id: '',
  competency_id: '',
  student_id: '',
  date_from: '',
  date_to: '',
}

export function filterQuery(filters: DashboardFilterState, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams()
  params.set('period', filters.period || '30d')
  if (filters.class_id) params.set('class_id', filters.class_id)
  if (filters.subject_id) params.set('subject_id', filters.subject_id)
  if (filters.competency_id) params.set('competency_id', filters.competency_id)
  if (filters.student_id) params.set('student_id', filters.student_id)
  if (filters.period === 'custom') {
    if (filters.date_from) params.set('date_from', filters.date_from)
    if (filters.date_to) params.set('date_to', filters.date_to)
  }
  for (const [key, value] of Object.entries(extra)) {
    if (value) params.set(key, value)
  }
  return params.toString()
}

/** Loads server-owned filter choices; the browser never invents identifiers. */
export function useDashboardFilterOptions() {
  const [options, setOptions] = useState<DashboardFilterOptions | null>(null)
  const [error, setError] = useState('')
  const { notify } = useToast()

  useEffect(() => {
    const controller = new AbortController()
    api<DashboardFilterOptions>('/dashboard/filters', { signal: controller.signal })
      .then((data) => {
        setOptions(data)
        const first = data.periods[0]?.value ?? '30d'
        setError('')
        return first
      })
      .catch((err) => {
        if ((err as Error).name === 'AbortError') return
        const message = errorMessage(err)
        setError(message)
        notify(message, 'error')
      })
    return () => controller.abort()
  }, [notify])

  return { options, error }
}

interface Props {
  options: DashboardFilterOptions | null
  value: DashboardFilterState
  onChange: (next: DashboardFilterState) => void
  includeStudent?: boolean
  disabled?: boolean
}

export function DashboardFilterBar({ options, value, onChange, includeStudent = true, disabled = false }: Props) {
  const set = (field: keyof DashboardFilterState, next: string) => {
    const updated = { ...value, [field]: next }
    if (field === 'subject_id') updated.competency_id = ''
    onChange(updated)
  }
  const competencies = options?.competencies.filter(
    (item) => !value.subject_id || item.subject_id === value.subject_id,
  ) ?? []

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field label="Periode">
        <Select
          aria-label="Periode"
          value={value.period}
          disabled={disabled}
          onChange={(event) => set('period', event.target.value)}
        >
          {(options?.periods ?? [{ value: '30d', label: '30 hari terakhir' }]).map((item) => (
            <option key={item.value} value={item.value}>{item.label}</option>
          ))}
        </Select>
      </Field>
      <Field label="Kelas">
        <Select
          aria-label="Kelas"
          value={value.class_id}
          disabled={disabled}
          onChange={(event) => set('class_id', event.target.value)}
        >
          <option value="">Semua kelas dalam cakupan</option>
          {(options?.classes ?? []).map((item) => (
            <option key={item.id} value={item.id}>{item.name}</option>
          ))}
        </Select>
      </Field>
      <Field label="Mata pelajaran">
        <Select
          aria-label="Mata pelajaran"
          value={value.subject_id}
          disabled={disabled}
          onChange={(event) => set('subject_id', event.target.value)}
        >
          <option value="">Semua mapel</option>
          {(options?.subjects ?? []).map((item) => (
            <option key={item.id} value={item.id}>{item.code ? `${item.code} — ${item.name}` : item.name}</option>
          ))}
        </Select>
      </Field>
      <Field label="Kompetensi">
        <Select
          aria-label="Kompetensi"
          value={value.competency_id}
          disabled={disabled}
          onChange={(event) => set('competency_id', event.target.value)}
        >
          <option value="">Semua kompetensi</option>
          {competencies.map((item) => (
            <option key={item.id} value={item.id}>{item.code ? `${item.code} — ${item.name}` : item.name}</option>
          ))}
        </Select>
      </Field>
      {includeStudent && (
        <Field label="Siswa" hint={options?.scope === 'self' ? 'Akun siswa hanya melihat dirinya sendiri.' : undefined}>
          <Select
            aria-label="Siswa"
            value={value.student_id}
            disabled={disabled}
            onChange={(event) => set('student_id', event.target.value)}
          >
            <option value="">Semua siswa dalam cakupan</option>
            {(options?.students ?? []).map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </Select>
        </Field>
      )}
      {value.period === 'custom' && (
        <>
          <Field label="Dari tanggal">
            <Input type="date" aria-label="Dari tanggal" value={value.date_from} disabled={disabled} onChange={(event) => set('date_from', event.target.value)} />
          </Field>
          <Field label="Sampai tanggal">
            <Input type="date" aria-label="Sampai tanggal" value={value.date_to} disabled={disabled} onChange={(event) => set('date_to', event.target.value)} />
          </Field>
        </>
      )}
      <div className="flex items-end gap-2">
        <Button variant="secondary" disabled={disabled} onClick={() => onChange({ ...DEFAULT_FILTERS, period: value.period })}>
          Atur ulang
        </Button>
      </div>
    </div>
  )
}
