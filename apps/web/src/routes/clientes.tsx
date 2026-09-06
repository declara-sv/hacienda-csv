import { Navigate, Outlet, createFileRoute } from '@tanstack/react-router'
import { useAuth } from '#/auth/AuthContext'
import { PageSkeleton } from '#/components/ui/Skeleton'

export const Route = createFileRoute('/clientes')({ component: ClientsLayout })

function ClientsLayout() {
  const { ready, session } = useAuth()

  if (!ready) {
    return <PageSkeleton />
  }

  if (!session) {
    return (
      <>
        <PageSkeleton />
        <Navigate to="/login" replace />
      </>
    )
  }

  return <Outlet />
}
