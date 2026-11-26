import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, clearCsrf, errorMessage, setCsrf } from '../lib/api'
import { kvGet, kvSet } from '../lib/offline'
import type { AppContext, User } from '../types'

interface LoginResult {
  csrf_token: string
  user: User
}

interface AuthValue {
  user: User | null
  context: AppContext | null
  loading: boolean
  offlineSnapshot: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [context, setContext] = useState<AppContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [offlineSnapshot, setOfflineSnapshot] = useState(false)

  const loadContext = useCallback(async () => {
    try {
      const data = await api<AppContext>('/portal/context')
      setContext(data)
      await kvSet('context', data)
    } catch {
      const cached = await kvGet<AppContext>('context')
      if (cached) setContext(cached)
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const me = await api<User>('/auth/me')
      setUser(me)
      setOfflineSnapshot(false)
      await kvSet('user', me)
      await loadContext()
    } catch (error) {
      const status = (error as { status?: number }).status
      if (status === 0) {
        const cached = await kvGet<User>('user')
        if (cached) {
          setUser(cached)
          setOfflineSnapshot(true)
          if (!context) {
            const cachedContext = await kvGet<AppContext>('context')
            if (cachedContext) setContext(cachedContext)
          }
        }
      }
      setUser((current) => (status === 401 ? null : current))
    } finally {
      setLoading(false)
    }
  }, [context, loadContext])

  useEffect(() => {
    void refresh()
    // Run once on mount; refresh() is intentionally not a dependency here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = useCallback(
    async (username: string, password: string) => {
      const result = await api<LoginResult>('/auth/login', {
        method: 'POST',
        body: { username, password },
      })
      setCsrf(result.csrf_token)
      setUser(result.user)
      setOfflineSnapshot(false)
      await kvSet('user', result.user)
      await loadContext()
      setLoading(false)
    },
    [loadContext],
  )

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST' })
    } catch {
      // Local logout must still succeed when the server is unreachable.
    }
    clearCsrf()
    setUser(null)
    setContext(null)
    setOfflineSnapshot(false)
  }, [])

  const changePassword = useCallback(async (current: string, next: string) => {
    await api('/auth/change-password', {
      method: 'POST',
      body: { current_password: current, new_password: next },
    })
  }, [])

  const value = useMemo<AuthValue>(
    () => ({ user, context, loading, offlineSnapshot, login, logout, refresh, changePassword }),
    [user, context, loading, offlineSnapshot, login, logout, refresh, changePassword],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth harus dipakai di dalam AuthProvider')
  return value
}

export function authError(error: unknown): string {
  return errorMessage(error)
}
