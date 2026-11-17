import { SignIn } from '@clerk/tanstack-react-start'
import { createFileRoute, redirect } from '@tanstack/react-router'
import { authCardAppearance } from '#/auth/clerk-appearance'
import { AFTER_AUTH_PATH, SIGN_IN_PATH, SIGN_UP_PATH } from '#/auth/paths'
import { isSignedIn } from '#/auth/session'
import { AuthLayout } from '#/components/AuthLayout'

// Clerk's multi-step flow uses sub-paths (/login/factor-one, ...), matched by
// the splat child route login.$.tsx; this route renders the form for all of them.
export const Route = createFileRoute('/login')({
  head: () => ({ meta: [{ title: 'Iniciar sesión | AnexosFácil' }] }),
  beforeLoad: async () => {
    if (await isSignedIn()) throw redirect({ to: AFTER_AUTH_PATH })
  },
  component: LoginPage,
})

function LoginPage() {
  return (
    <AuthLayout>
      <SignIn
        routing="path"
        path={SIGN_IN_PATH}
        signUpUrl={SIGN_UP_PATH}
        fallbackRedirectUrl={AFTER_AUTH_PATH}
        appearance={authCardAppearance}
      />
    </AuthLayout>
  )
}
