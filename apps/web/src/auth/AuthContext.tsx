import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { authApi } from '#/lib/api-client'
import { clearSession, readSession, writeSession } from './auth-storage'
import type { AuthSession } from '#/lib/api-types'

type AuthContextValue = {
  /** False until the session has been read from storage on the client. */
  ready: boolean
  session: AuthSession | null
  login: (email: string, password: string) => Promise<void>
  register: (fullName: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Start empty on both server and client so the first render matches during
  // hydration, then read localStorage once mounted.
  const [session, setSession] = useState<AuthSession | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setSession(readSession())
    setReady(true)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      ready,
      session,
      login: async (email, password) => {
        const nextSession = await authApi.login({ email, password })
        writeSession(nextSession)
        setSession(nextSession)
      },
      register: async (fullName, email, password) => {
        const nextSession = await authApi.register({
          fullName,
          email,
          password,
        })
        writeSession(nextSession)
        setSession(nextSession)
      },
      logout: async () => {
        try {
          if (session?.refreshToken) {
            await authApi.logout(session.refreshToken)
          }
        } finally {
          clearSession()
          setSession(null)
        }
      },
    }),
    [ready, session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth debe usarse dentro de AuthProvider')
  }

  return context
}
