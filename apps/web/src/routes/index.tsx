import { Navigate, createFileRoute } from '@tanstack/react-router'
import { useAuth } from '#/auth/AuthContext'

export const Route = createFileRoute('/')({ component: HomeRedirect })

function HomeRedirect() {
  const { session } = useAuth()

  if (session) {
    return <Navigate to="/clientes" />
  }

  return <Navigate to="/login" />
}
