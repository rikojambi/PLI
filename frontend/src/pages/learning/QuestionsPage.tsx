import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Badge, Button, Card, Checkbox, EmptyState, Field, Input, Modal, Select, Spinner, Textarea } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../context/AuthContext'
import { api, errorMessage } from '../../lib/api'
import { QUESTION_TYPES, type QuestionOption, type QuestionRow, type QuestionType } from '../../types'

interface Competency {
  id: string
  subject_id: string
  code: string
  name: string
}

interface OptionDraft {
  key: string
  label: string
  content: string
  is_correct: boolean
  match_key: string
}

let optionCounter = 0
function newOption(label?: string): OptionDraft {
  optionCounter += 1
  return { key: `new-${optionCounter}`, label: label ?? String.fromCharCode(65 + optionCounter % 26), content: '', is_correct: false, match_key: '' }
}

const OBJECTIVE_TYPES: QuestionType[] = [
  'multiple_choice', 'multiple_response', 'true_false', 'matching', 'image_based',
]
const MANUAL_TYPES: QuestionType[] = ['essay', 'stepped_essay', 'project']
const TEXT_TYPES: QuestionType[] = ['short_answer', 'fill_blank']

function typeLabel(value: QuestionType): string {
  return QUESTION_TYPES.find((type) => type.value === value)?.label ?? value
}

export function QuestionsPage() {
  const { context } = useAuth()
  const { notify } = useToast()
  const [rows, setRows] = useState<QuestionRow[] | null>(null)
  const [competencies, setCompetencies] = useState<Competency[]>([])
  const [subjectFilter, setSubjectFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<QuestionRow | null>(null)
  const [busy, setBusy] = useState(false)

  const [subjectId, setSubjectId] = useState('')
  const [competencyId, setCompetencyId] = useState('')
  const [questionType, setQuestionType] = useState<QuestionType>('multiple_choice')
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium')
  const [content, setContent] = useState('')
  const [points, setPoints] = useState(10)
  const [timeLimit, setTimeLimit] = useState('')
  const [explanation, setExplanation] = useState('')
  const [expected, setExpected] = useState('')
  const [imagePath, setImagePath] = useState('')
  const [published, setPublished] = useState(true)
  const [options, setOptions] = useState<OptionDraft[]>([newOption('A'), newOption('B')])

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (subjectFilter) params.set('subject_id', subjectFilter)
      if (typeFilter) params.set('question_type', typeFilter)
      const query = params.toString() ? `?${params.toString()}` : ''
      setRows(await api<QuestionRow[]>(`/learning/questions${query}`))
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [subjectFilter, typeFilter])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!subjectId) {
      setCompetencies([])
      return
    }
    void api<Competency[]>(`/admin/competencies?subject_id=${encodeURIComponent(subjectId)}`)
      .then(setCompetencies)
      .catch(() => setCompetencies([]))
  }, [subjectId])

  const openForm = (row: QuestionRow | null) => {
    setEditing(row)
    setSubjectId(row?.subject_id || subjectFilter || context?.subjects[0]?.id || '')
    setCompetencyId(row?.competency_id ?? '')
    setQuestionType(row?.question_type ?? 'multiple_choice')
    setDifficulty(row?.difficulty ?? 'medium')
    setContent(row?.content ?? '')
    setPoints(row?.points ?? 10)
    setTimeLimit(row?.time_limit_sec ? String(row.time_limit_sec) : '')
    setExplanation(row?.explanation ?? '')
    setExpected(Array.isArray(row?.rubric_json?.expected) ? (row.rubric_json.expected as string[]).join(', ') : String(row?.rubric_json?.expected ?? ''))
    setImagePath(row?.image_path ?? '')
    setPublished(row?.is_published ?? true)
    setOptions(row && row.options.length > 0
      ? row.options.map((option: QuestionOption) => ({
          key: option.id,
          label: option.label,
          content: option.content,
          is_correct: Boolean(option.is_correct),
          match_key: option.match_key ?? '',
        }))
      : [newOption('A'), newOption('B')])
    setShowForm(true)
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (content.trim().length < 3) {
      notify('Teks soal minimal 3 karakter.', 'error')
      return
    }
    const correctCount = options.filter((option) => option.is_correct).length
    if (OBJECTIVE_TYPES.includes(questionType) && options.length < 2) {
      notify('Soal objektif memerlukan minimal dua pilihan.', 'error')
      return
    }
    if (questionType === 'multiple_choice' && correctCount !== 1) {
      notify('Pilihan ganda harus memiliki tepat satu kunci jawaban.', 'error')
      return
    }
    if (questionType === 'multiple_response' && correctCount < 1) {
      notify('Pilihan ganda kompleks minimal memiliki satu kunci jawaban.', 'error')
      return
    }
    if (TEXT_TYPES.includes(questionType) && !expected.trim()) {
      notify('Isian singkat/melengkapi memerlukan kunci jawaban.', 'error')
      return
    }
    if (questionType === 'matching' && options.some((option) => !option.match_key.trim())) {
      notify('Setiap pilihan pada soal menjodohkan memerlukan pasangan.', 'error')
      return
    }

    setBusy(true)
    try {
      const body = {
        subject_id: subjectId,
        competency_id: competencyId || null,
        question_type: questionType,
        difficulty,
        content: content.trim(),
        image_path: imagePath || null,
        points: Number(points),
        time_limit_sec: timeLimit ? Number(timeLimit) : null,
        explanation: explanation || null,
        rubric_json: expected.trim()
          ? { expected: expected.split(',').map((item) => item.trim()).filter(Boolean) }
          : {},
        options: OBJECTIVE_TYPES.includes(questionType)
          ? options.map((option, index) => ({
              label: option.label || String.fromCharCode(65 + index),
              content: option.content,
              is_correct: option.is_correct || null,
              match_key: option.match_key.trim() || null,
              position: index,
            }))
          : [],
        is_published: published,
      }
      if (editing) {
        await api(`/learning/questions/${editing.id}`, { method: 'PATCH', body })
        notify('Soal diperbarui')
      } else {
        await api('/learning/questions', { method: 'POST', body })
        notify('Soal dibuat')
      }
      setShowForm(false)
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (row: QuestionRow) => {
    if (!window.confirm(`Hapus soal "${row.content.slice(0, 50)}…"?`)) return
    try {
      await api(`/learning/questions/${row.id}`, { method: 'DELETE' })
      notify('Soal dihapus')
      await load()
    } catch (err) {
      notify(errorMessage(err), 'error')
    }
  }

  const needsOptions = OBJECTIVE_TYPES.includes(questionType)
  const needsExpected = TEXT_TYPES.includes(questionType)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Bank soal</h1>
          <p className="mt-1 text-sm text-slate-500">Sepuluh tipe soal dengan kunci jawaban dan rubrik yang divalidasi server.</p>
        </div>
        <Button onClick={() => openForm(null)}>Tambah soal</Button>
      </div>

      <Card className="grid gap-3 sm:grid-cols-2">
        <Field label="Mata pelajaran">
          <Select value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)}>
            <option value="">Semua</option>
            {context?.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
          </Select>
        </Field>
        <Field label="Tipe soal">
          <Select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="">Semua tipe</option>
            {QUESTION_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
          </Select>
        </Field>
      </Card>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      {!rows ? <Spinner label="Memuat soal…" /> : rows.length === 0 ? (
        <Card><EmptyState message="Belum ada soal. Buat soal pertama Anda." /></Card>
      ) : (
        <div className="space-y-3">
          {rows.map((row) => (
            <Card key={row.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={MANUAL_TYPES.includes(row.question_type) ? 'amber' : 'indigo'}>{typeLabel(row.question_type)}</Badge>
                    <Badge tone={row.is_published ? 'green' : 'slate'}>{row.is_published ? 'Aktif' : 'Draft'}</Badge>
                    <span className="text-xs text-slate-400">{row.points} poin · {row.difficulty}</span>
                  </div>
                  <p className="mt-2 text-sm text-slate-800">{row.content}</p>
                  {row.options.length > 0 && (
                    <p className="mt-1 text-xs text-slate-500">
                      {row.options.map((option) => `${option.label}. ${option.content}${option.is_correct ? ' ✓' : ''}`).join('  |  ')}
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => openForm(row)}>Ubah</Button>
                  <Button variant="danger" onClick={() => void remove(row)}>Hapus</Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {showForm && (
        <Modal title={editing ? 'Ubah soal' : 'Soal baru'} onClose={() => setShowForm(false)}>
          <form className="space-y-4" onSubmit={(event) => void save(event)}>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Mata pelajaran">
                <Select value={subjectId} onChange={(event) => { setSubjectId(event.target.value); setCompetencyId('') }}>
                  {context?.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
                </Select>
              </Field>
              <Field label="Kompetensi (opsional)">
                <Select value={competencyId} onChange={(event) => setCompetencyId(event.target.value)}>
                  <option value="">Tanpa kompetensi</option>
                  {competencies.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}
                </Select>
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Tipe soal">
                <Select value={questionType} onChange={(event) => setQuestionType(event.target.value as QuestionType)}>
                  {QUESTION_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                </Select>
              </Field>
              <Field label="Kesulitan">
                <Select value={difficulty} onChange={(event) => setDifficulty(event.target.value as typeof difficulty)}>
                  <option value="easy">Mudah</option><option value="medium">Sedang</option><option value="hard">Sulit</option>
                </Select>
              </Field>
              <Field label="Poin">
                <Input type="number" min={1} max={100} step={0.5} value={points} onChange={(event) => setPoints(Number(event.target.value))} />
              </Field>
            </div>
            <Field label="Teks soal">
              <Textarea rows={3} value={content} onChange={(event) => setContent(event.target.value)} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Batas waktu per soal (detik, opsional)">
                <Input type="number" min={10} max={3600} value={timeLimit} onChange={(event) => setTimeLimit(event.target.value)} />
              </Field>
              <Field label="URL gambar (opsional)">
                <Input value={imagePath} onChange={(event) => setImagePath(event.target.value)} placeholder="/api/v1/learning/files/…" />
              </Field>
            </div>
            <Field label="Pembahasan (opsional, muncul setelah pengumpulan)">
              <Textarea rows={2} value={explanation} onChange={(event) => setExplanation(event.target.value)} />
            </Field>

            {needsExpected && (
              <Field label="Kunci jawaban" hint="Pisahkan beberapa jawaban yang diterima dengan koma.">
                <Input value={expected} onChange={(event) => setExpected(event.target.value)} placeholder="4, empat" />
              </Field>
            )}

            {needsOptions && (
              <div className="space-y-3 rounded-xl border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold">Pilihan jawaban</p>
                  <Button variant="secondary" className="min-h-[36px] px-3" onClick={() => setOptions((current) => [...current, newOption()])}>
                    + Pilihan
                  </Button>
                </div>
                {options.map((option, index) => (
                  <div key={option.key} className="grid gap-2 sm:grid-cols-[60px_1fr_1fr_auto_auto] sm:items-center">
                    <Input value={option.label} onChange={(event) => setOptions((current) => current.map((item) => item.key === option.key ? { ...item, label: event.target.value } : item))} aria-label={`Label ${index + 1}`} />
                    <Input value={option.content} onChange={(event) => setOptions((current) => current.map((item) => item.key === option.key ? { ...item, content: event.target.value } : item))} placeholder="Teks pilihan" />
                    <Input
                      value={option.match_key}
                      onChange={(event) => setOptions((current) => current.map((item) => item.key === option.key ? { ...item, match_key: event.target.value } : item))}
                      placeholder={questionType === 'matching' ? 'Kunci pasangan' : 'Pasangan (opsional)'}
                    />
                    <Checkbox
                      label="Benar"
                      checked={option.is_correct}
                      onChange={(event) => {
                        const checked = event.target.checked
                        setOptions((current) => current.map((item) => {
                          if (item.key === option.key) return { ...item, is_correct: checked }
                          if (checked && questionType === 'multiple_choice') return { ...item, is_correct: false }
                          return item
                        }))
                      }}
                    />
                    <Button variant="ghost" className="px-2" onClick={() => setOptions((current) => current.filter((item) => item.key !== option.key))} aria-label="Hapus pilihan">✕</Button>
                  </div>
                ))}
                {questionType === 'matching' && <p className="text-xs text-slate-500">Kunci pasangan yang sama akan menjadi daftar pilihan pada soal menjodohkan.</p>}
              </div>
            )}

            {MANUAL_TYPES.includes(questionType) && (
              <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Jawaban tipe ini dinilai manual oleh guru dan tidak memengaruhi nilai otomatis.</p>
            )}

            <Checkbox label="Soal aktif digunakan" checked={published} onChange={(event) => setPublished(event.target.checked)} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Batal</Button>
              <Button type="submit" disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan soal'}</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
