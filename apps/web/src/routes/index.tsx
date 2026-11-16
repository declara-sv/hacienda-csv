import { createFileRoute, redirect } from '@tanstack/react-router'
import { AFTER_AUTH_PATH, SIGN_IN_PATH } from '#/auth/paths'
import { isSignedIn } from '#/auth/session'

export const Route = createFileRoute('/')({
  beforeLoad: async () => {
    throw redirect({
      to: (await isSignedIn()) ? AFTER_AUTH_PATH : SIGN_IN_PATH,
      replace: true,
    })
  },
})
