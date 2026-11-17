import { SignUp } from '@clerk/tanstack-react-start'
import { createFileRoute, redirect } from '@tanstack/react-router'
import { authCardAppearance } from '#/auth/clerk-appearance'
import { AFTER_AUTH_PATH, SIGN_IN_PATH, SIGN_UP_PATH } from '#/auth/paths'
import { isSignedIn } from '#/auth/session'
import { AuthLayout } from '#/components/AuthLayout'

// Clerk's multi-step flow uses sub-paths (/signup/verify-email-address, ...),
// matched by the splat child route signup.$.tsx.
export const Route = createFileRoute('/signup')({
  head: () => ({ meta: [{ title: 'Crear cuenta | AnexosFácil' }] }),
  beforeLoad: async () => {
    if (await isSignedIn()) throw redirect({ to: AFTER_AUTH_PATH })
  },
  component: RegisterPage,
})

function RegisterPage() {
  return (
    <AuthLayout>
      <SignUp
        routing="path"
        path={SIGN_UP_PATH}
        signInUrl={SIGN_IN_PATH}
        fallbackRedirectUrl={AFTER_AUTH_PATH}
        appearance={authCardAppearance}
      />
    </AuthLayout>
  )
}
