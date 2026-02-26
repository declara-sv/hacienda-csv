import { createContext, useContext, useMemo, useState } from 'react'
import { authApi } from '#/lib/api-client'
import { clearSession, readSession, writeSession } from './auth-storage'
import type { AuthSession } from '#/lib/api-types'

type AuthContextValue = {
  session: AuthSession | null
  login: (email: string, password: string) => Promise<void>
  register: (fullName: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(() => readSession())

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      login: async (email, password) => {
        const nextSession = await authApi.login({ email, password })
        writeSession(nextSession)
        setSession(nextSession)
      },
      register: async (fullName, email, password) => {
        const nextSession = await authApi.register({ fullName, email, password })
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
    [session],
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
