import { Navigate, Outlet, createFileRoute } from '@tanstack/react-router'
import { useAuth } from '#/auth/AuthContext'

export const Route = createFileRoute('/clientes')({ component: ClientsLayout })

function ClientsLayout() {
  const { session } = useAuth()

  if (!session) {
    return <Navigate to="/login" />
  }

  return <Outlet />
}
