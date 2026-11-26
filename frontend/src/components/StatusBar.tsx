import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { queuedAnswers } from '../lib/offline'
import { Icon } from './Icons'

export function StatusBar() {
  const { refresh, offlineSnapshot } = useAuth()
  const [online, setOnline] = useState(navigator.onLine)
  const [queued, setQueued] = useState(0)

  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    const loadQueue = async () => setQueued((await queuedAnswers()).length)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    window.addEventListener('pli:queue-changed', loadQueue)
    void loadQueue()
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
      window.removeEventListener('pli:queue-changed', loadQueue)
    }
  }, [])

  const tone = online && !offlineSnapshot ? 'text-emerald-600' : 'text-amber-600'

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className={`inline-flex items-center gap-1.5 font-semibold ${tone}`}>
        <Icon name={online ? 'online' : 'offline'} className="h-4 w-4" />
        {online ? (offlineSnapshot ? 'Data lokal' : 'Online') : 'Offline'}
      </span>
      {queued > 0 && <span className="text-slate-500">{queued} jawaban menunggu sinkron</span>}
      {online && !offlineSnapshot && (
        <button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-1 font-medium text-brand-600 hover:underline">
          <Icon name="refresh" className="h-3.5 w-3.5" /> Segarkan
        </button>
      )}
    </div>
  )
}
