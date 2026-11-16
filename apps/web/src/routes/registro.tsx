import { SignUp } from '@clerk/tanstack-react-start'
import { createFileRoute, redirect } from '@tanstack/react-router'
import { authCardAppearance } from '#/auth/clerk-appearance'
import { AFTER_AUTH_PATH, SIGN_IN_PATH, SIGN_UP_PATH } from '#/auth/paths'
import { isSignedIn } from '#/auth/session'
import { AuthLayout } from '#/components/AuthLayout'
import { useI18n } from '#/i18n/I18nProvider'

// Clerk's multi-step flow uses sub-paths (/registro/verify-email-address, ...),
// matched by the splat child route registro.$.tsx.
export const Route = createFileRoute('/registro')({
  head: () => ({ meta: [{ title: 'Crear cuenta | HaciendaCSV' }] }),
  beforeLoad: async () => {
    if (await isSignedIn()) throw redirect({ to: AFTER_AUTH_PATH })
  },
  component: RegisterPage,
})

function RegisterPage() {
  const { t } = useI18n()

  return (
    <AuthLayout title={t('authTitleRegister')} intro={t('authIntroRegister')}>
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
