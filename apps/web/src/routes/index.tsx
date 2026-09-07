import { Navigate, createFileRoute } from '@tanstack/react-router'
import { useAuth } from '#/auth/AuthContext'
import { PageSkeleton } from '#/components/ui/Skeleton'

export const Route = createFileRoute('/')({ component: HomeRedirect })

function HomeRedirect() {
  const { ready, session } = useAuth()

  return (
    <>
      <PageSkeleton />
      {ready ? (
        <Navigate to={session ? '/clientes' : '/login'} replace />
      ) : null}
    </>
  )
}
