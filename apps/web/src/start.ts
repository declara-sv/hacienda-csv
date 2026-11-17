import { clerkMiddleware } from '@clerk/tanstack-react-start/server'
import { createCsrfMiddleware, createStart } from '@tanstack/react-start'
import { SIGN_IN_PATH, SIGN_UP_PATH } from '#/auth/paths'

// Start only adds its default CSRF check when src/start.ts is absent, so it is
// added here: server function calls must come from this origin.
const csrfMiddleware = createCsrfMiddleware({
  filter: (ctx) => ctx.handlerType === 'serverFn',
})

// clerkMiddleware() only reads the session; routes are protected in beforeLoad
// (see src/auth/session.ts).
export const startInstance = createStart(() => ({
  requestMiddleware: [
    csrfMiddleware,
    clerkMiddleware({ signInUrl: SIGN_IN_PATH, signUpUrl: SIGN_UP_PATH }),
  ],
}))
