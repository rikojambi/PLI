import { useEffect, useState } from 'react'
import { Icon } from './Icons'
import { Button } from './ui'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    const standalone = window.matchMedia('(display-mode: standalone)').matches
    if (standalone) return
    const handler = (event: Event) => {
      event.preventDefault()
      setDeferred(event as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  if (!deferred || dismissed) return null

  return (
    <div className="fixed bottom-20 left-4 right-4 z-30 mx-auto max-w-sm rounded-2xl border border-brand-100 bg-white p-4 shadow-xl sm:bottom-6">
      <div className="flex items-start gap-3">
        <span className="rounded-xl bg-brand-50 p-2 text-brand-600"><Icon name="install" /></span>
        <div className="flex-1">
          <p className="text-sm font-semibold text-slate-900">Pasang PLI di perangkat ini</p>
          <p className="mt-1 text-xs text-slate-500">Akses lebih cepat dan tetap bisa membuka data tersimpan saat offline.</p>
          <div className="mt-3 flex gap-2">
            <Button
              className="flex-1 py-1.5"
              onClick={async () => {
                await deferred.prompt()
                await deferred.userChoice
                setDeferred(null)
              }}
            >
              Pasang
            </Button>
            <Button variant="ghost" className="py-1.5" onClick={() => setDismissed(true)}>Nanti</Button>
          </div>
        </div>
      </div>
    </div>
  )
}
