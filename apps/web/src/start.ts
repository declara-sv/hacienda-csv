import { clerkMiddleware } from '@clerk/tanstack-react-start/server'
import { createStart } from '@tanstack/react-start'
import { SIGN_IN_PATH, SIGN_UP_PATH } from '#/auth/paths'

// clerkMiddleware() only reads the session; routes are protected in beforeLoad
// (see src/auth/session.ts).
export const startInstance = createStart(() => ({
  requestMiddleware: [
    clerkMiddleware({ signInUrl: SIGN_IN_PATH, signUpUrl: SIGN_UP_PATH }),
  ],
}))
