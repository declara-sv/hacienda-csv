import { createFileRoute, redirect } from '@tanstack/react-router'
import { SIGN_IN_PATH } from '#/auth/paths'
import { isSignedIn } from '#/auth/session'

export const Route = createFileRoute('/clients')({
  beforeLoad: async () => {
    if (!(await isSignedIn())) throw redirect({ to: SIGN_IN_PATH })
  },
})
