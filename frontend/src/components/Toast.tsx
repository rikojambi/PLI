import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type ToastKind = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  kind: ToastKind
  message: string
}

interface ToastValue {
  notify: (message: string, kind?: ToastKind) => void
}

const ToastContext = createContext<ToastValue | null>(null)
let counter = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const notify = useCallback((message: string, kind: ToastKind = 'success') => {
    const id = ++counter
    setItems((current) => [...current, { id, kind, message }])
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 4500)
  }, [])

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 bottom-24 z-50 flex flex-col items-center gap-2 sm:bottom-6">
        {items.map((item) => (
          <div
            key={item.id}
            role="status"
            className={`pointer-events-auto max-w-md rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${
              item.kind === 'error'
                ? 'bg-rose-600'
                : item.kind === 'info'
                  ? 'bg-slate-700'
                  : 'bg-emerald-600'
            }`}
          >
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast harus dipakai di dalam ToastProvider')
  return value
}
