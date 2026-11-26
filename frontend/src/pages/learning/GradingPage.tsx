import { useCallback, useEffect, useState } from 'react'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, Select, Spinner, Textarea } from '../../components/ui'
import { useToast } from '../../components/Toast'
import { api, errorMessage } from '../../lib/api'
import type { AnswerRow, AttemptRow, QuestionRow, ResultRow } from '../../types'

interface PortalClass { id: string; name: string }
const MANUAL_TYPES = new Set(['essay', 'stepped_essay', 'project'])

export function GradingPage() {
  const { notify } = useToast()
  const [results, setResults] = useState<ResultRow[] | null>(null)
  const [classes, setClasses] = useState<PortalClass[]>([])
  const [classId, setClassId] = useState('')
  const [selected, setSelected] = useState<ResultRow | null>(null)
  const [attempt, setAttempt] = useState<AttemptRow | null>(null)
  const [answers, setAnswers] = useState<AnswerRow[]>([])
  const [points, setPoints] = useState<Record<string, string>>({})
  const [feedback, setFeedback] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadResults = useCallback(async () => {
    try {
      const query = classId ? `?class_id=${encodeURIComponent(classId)}` : ''
      setResults(await api<ResultRow[]>(`/learning/results${query}`))
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [classId])

  useEffect(() => {
    void loadResults()
  }, [loadResults])

  useEffect(() => {
    void api<PortalClass[]>('/portal/teacher/classes').then(setClasses).catch(() => setClasses([]))
  }, [])

  const openResult = async (row: ResultRow) => {
    setSelected(row)
    setAttempt(null)
    setAnswers([])
    try {
      const [loadedAttempt, loadedAnswers] = await Promise.all([
        api<AttemptRow>(`/learning/attempts/${row.attempt_id}`),
        api<AnswerRow[]>(`/learning/attempts/${row.attempt_id}/answers`),
      ])
      setAttempt(loadedAttempt)
      setAnswers(loadedAnswers)
      const nextPoints: Record<string, string> = {}
      const nextFeedback: Record<string, string> = {}
      for (const answer of loadedAnswers) {
        nextPoints[answer.id] = answer.points_earned === null ? '' : String(answer.points_earned)
        const existing = typeof answer.answer_json?.teacher_feedback === 'string' ? answer.answer_json.teacher_feedback : ''
        nextFeedback[answer.id] = existing
      }
      setPoints(nextPoints)
      setFeedback(nextFeedback)
    } catch (err) {
      notify(errorMessage(err), 'error')
    }
  }

  const grade = async (answer: AnswerRow) => {
    setBusy(true)
    try {
      await api(`/learning/answers/${answer.id}/grade`, {
        method: 'PATCH',
        body: { points_earned: Number(points[answer.id] ?? 0), feedback: feedback[answer.id] || null },
      })
      notify('Nilai tersimpan dan hasil dihitung ulang')
      await openResult(selected!)
      await loadResults()
    } catch (err) {
      notify(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const questionById = (id: string): QuestionRow | undefined => attempt?.questions.find((item) => item.id === id)

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Koreksi jawaban</h1>
        <p className="mt-1 text-sm text-slate-500">Hanya jawaban uraian/proyek yang dinilai manual. Nilai dihitung ulang setelah setiap koreksi.</p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-5 lg:grid-cols-[minmax(280px,0.9fr)_minmax(0,1.4fr)]">
        <Card>
          <CardTitle title="Daftar hasil" subtitle="Pilih satu upaya untuk melihat jawaban." />
          <div className="mb-3">
            <Select value={classId} onChange={(event) => setClassId(event.target.value)}>
              <option value="">Semua kelas</option>
              {classes.map((klass) => <option key={klass.id} value={klass.id}>{klass.name}</option>)}
            </Select>
          </div>
          {!results ? <Spinner label="Memuat hasil…" /> : results.length === 0 ? (
            <EmptyState message="Belum ada hasil asesmen." />
          ) : (
            <div className="max-h-[65vh] space-y-2 overflow-y-auto">
              {results.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  onClick={() => void openResult(row)}
                  className={`w-full rounded-xl border p-3 text-left text-sm ${selected?.id === row.id ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:bg-slate-50'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{row.student_name ?? 'Siswa'}</span>
                    <Badge tone={row.score >= 70 ? 'green' : 'amber'}>{row.score}%</Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{row.assessment_title ?? 'Asesmen'}</p>
                  <p className="mt-1 text-xs text-slate-400">{new Date(row.graded_at).toLocaleString('id-ID')}</p>
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardTitle
            title={selected ? `Jawaban — ${selected.student_name ?? 'Siswa'}` : 'Detail jawaban'}
            subtitle={selected?.assessment_title ?? undefined}
          />
          {!selected ? <EmptyState message="Pilih hasil di sebelah kiri." /> : !attempt ? (
            <Spinner label="Memuat jawaban…" />
          ) : answers.length === 0 ? (
            <EmptyState message="Upaya ini tidak memiliki jawaban tersimpan." />
          ) : (
            <div className="space-y-4">
              {attempt.anomaly_flags.length > 0 && (
                <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">
                  Indikator untuk ditinjau: {attempt.anomaly_flags.join(', ')}. Bukan dasar penilaian otomatis.
                </p>
              )}
              {answers.map((answer) => {
                const question = questionById(answer.question_id)
                const manual = question ? MANUAL_TYPES.has(question.question_type) : false
                const text = typeof answer.answer_json?.text === 'string'
                  ? answer.answer_json.text
                  : JSON.stringify(answer.answer_json)
                return (
                  <div key={answer.id} className="rounded-xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium text-slate-800">{question?.content ?? answer.question_id}</p>
                      <Badge tone={manual ? 'amber' : 'green'}>{manual ? 'Menunggu koreksi' : 'Otomatis'}</Badge>
                    </div>
                    <p className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{text || '(kosong)'}</p>
                    {typeof answer.answer_json?.file_path === 'string' && answer.answer_json.file_path && (
                      <a className="mt-2 inline-block text-sm font-semibold text-brand-700 underline" href={answer.answer_json.file_path} target="_blank" rel="noreferrer">Buka lampiran ↗</a>
                    )}
                    {manual && (
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <Field label={`Poin (maks ${question?.points ?? '-'})`}>
                          <Input
                            type="number"
                            min={0}
                            max={question?.points}
                            step={0.5}
                            value={points[answer.id] ?? ''}
                            onChange={(event) => setPoints((current) => ({ ...current, [answer.id]: event.target.value }))}
                          />
                        </Field>
                        <Field label="Catatan untuk siswa">
                          <Textarea
                            rows={2}
                            value={feedback[answer.id] ?? ''}
                            onChange={(event) => setFeedback((current) => ({ ...current, [answer.id]: event.target.value }))}
                          />
                        </Field>
                        <div className="sm:col-span-2">
                          <Button onClick={() => void grade(answer)} disabled={busy}>
                            {busy ? 'Menyimpan…' : 'Simpan nilai'}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
