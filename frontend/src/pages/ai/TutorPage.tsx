import { useEffect, useState } from 'react'
import { Badge, Button, Card, CardTitle, EmptyState, Field, Spinner, Textarea } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import type { TutorChatResult, TutorConversation } from '../../types'

function newClientId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `tutor-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function TutorPage() {
  const [conversations, setConversations] = useState<TutorConversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [active, setActive] = useState<TutorConversation | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const loadList = () => {
    void api<TutorConversation[]>('/ai/tutor/conversations')
      .then((value) => { setConversations(value); setError('') })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }
  useEffect(loadList, [])

  useEffect(() => {
    if (!activeId) { setActive(null); return }
    void api<TutorConversation>(`/ai/tutor/conversations/${activeId}`)
      .then(setActive)
      .catch((err) => setError(errorMessage(err)))
  }, [activeId])

  const send = async () => {
    if (message.trim().length < 1) return
    setBusy(true)
    setError('')
    const clientId = newClientId()
    const text = message.trim()
    setMessage('')
    try {
      const result = await api<TutorChatResult>('/ai/tutor/chat', {
        method: 'POST',
        body: { message: text, conversation_id: activeId ?? undefined, client_id: clientId },
      })
      setActiveId(result.conversation_id)
      setActive(await api<TutorConversation>(`/ai/tutor/conversations/${result.conversation_id}`))
      loadList()
      if (!result.available) setError('Jawaban AI belum tersedia. Profil penguasaan tetap dapat dilihat pada halaman Penguasaan.')
    } catch (err) {
      setError(errorMessage(err))
      setMessage(text)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">AI Tutor</h1>
        <p className="mt-1 text-sm text-slate-500">
          Tutor menyesuaikan penjelasan dengan profil penguasaan Anda sendiri. Tutor tidak memberi vonis dan
          tidak mengakses percakapan siswa lain. Jika layanan belum dikonfigurasi, aplikasi menyatakannya terus terang.
        </p>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <Card>
          <CardTitle title="Percakapan" />
          {loading ? <Spinner label="Memuat…" /> : conversations.length === 0 ? <EmptyState message="Belum ada percakapan." /> : (
            <div className="space-y-2">
              {conversations.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveId(item.id)}
                  className={`w-full rounded-xl px-3 py-2 text-left text-sm ${activeId === item.id ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100'}`}
                >
                  <span className="line-clamp-2 block font-medium">{item.title}</span>
                  <span className="text-[11px] text-slate-400">{new Date(item.updated_at).toLocaleDateString('id-ID')}</span>
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardTitle title="Percakapan aktif" subtitle="Kirim pertanyaan tentang materi yang belum dipahami." />
          {active && active.messages.length > 0 ? (
            <div className="mb-4 max-h-[55vh] space-y-3 overflow-y-auto pr-1">
              {active.messages.map((item) => (
                <div key={item.id} className={`rounded-xl p-3 text-sm ${item.role === 'user' ? 'ml-8 bg-brand-50 text-brand-900' : 'mr-8 bg-slate-50 text-slate-700'}`}>
                  <div className="mb-1 flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-slate-400">
                    <span>{item.role === 'user' ? 'Anda' : 'Tutor'}</span>
                    {item.sources_json.length > 0 && <Badge>{item.sources_json.length} sumber</Badge>}
                  </div>
                  <p className="whitespace-pre-wrap">{item.content}</p>
                </div>
              ))}
            </div>
          ) : <EmptyState message="Belum ada pesan. Mulai dengan menanyakan satu konsep yang sulit." />}

          <Field label="Pertanyaan Anda">
            <Textarea rows={3} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Misalnya: mengapa hasil 3 × 4 = 12?" />
          </Field>
          <div className="mt-4 flex justify-end"><Button onClick={() => void send()} disabled={busy || message.trim().length === 0}>{busy ? 'Menunggu jawaban…' : 'Kirim'}</Button></div>
        </Card>
      </div>
    </div>
  )
}
