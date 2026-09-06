import {
  Link,
  Navigate,
  createFileRoute,
  useNavigate,
} from '@tanstack/react-router'
import { useState } from 'react'
import { useAuth } from '#/auth/AuthContext'
import { AuthLayout } from '#/components/AuthLayout'
import { Button } from '#/components/ui/Button'
import { Field, Input, fieldDescribedBy } from '#/components/ui/Field'
import { Notice } from '#/components/ui/Notice'
import { PasswordInput } from '#/components/ui/PasswordInput'
import { useI18n } from '#/i18n/I18nProvider'
import { ApiError } from '#/lib/api-client'

export const Route = createFileRoute('/login')({
  head: () => ({ meta: [{ title: 'Iniciar sesión | HaciendaCSV' }] }),
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const { ready, session, login } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (ready && session && !loading) {
    return <Navigate to="/clientes" replace />
  }

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setLoading(true)

    try {
      await login(email, password)
      await navigate({ to: '/clientes' })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('authErrorLogin'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title={t('authTitleLogin')}
      intro={t('authIntroLogin')}
      footer={
        <Link
          to="/registro"
          className="font-semibold text-accent hover:underline"
        >
          {t('authToRegister')}
        </Link>
      }
    >
      <form className="space-y-5" onSubmit={onSubmit}>
        <Field id="email" label={t('authEmail')}>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>

        <Field
          id="password"
          label={t('authPassword')}
          hint={t('authPasswordHint')}
        >
          <PasswordInput
            id="password"
            name="password"
            autoComplete="current-password"
            required
            minLength={8}
            aria-describedby={fieldDescribedBy(
              'password',
              t('authPasswordHint'),
            )}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        {error ? (
          <Notice variant="error" onDismiss={() => setError(null)}>
            {error}
          </Notice>
        ) : null}

        <Button
          type="submit"
          className="w-full"
          loading={loading}
          loadingLabel={t('authSubmittingLogin')}
        >
          {t('authSubmitLogin')}
        </Button>
      </form>
    </AuthLayout>
  )
}
