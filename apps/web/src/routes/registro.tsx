import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useAuth } from '#/auth/AuthContext'
import { ApiError } from '#/lib/api-client'
import { useI18n } from '#/i18n/I18nProvider'

export const Route = createFileRoute('/registro')({ component: RegisterPage })

function RegisterPage() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const { register } = useAuth()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setLoading(true)

    try {
      await register(fullName, email, password)
      await navigate({ to: '/clientes' })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo crear la cuenta.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="mx-auto max-w-lg rounded-3xl border border-[#1f3d45]/20 bg-white/80 p-8 shadow-[0_24px_60px_-30px_rgba(16,47,59,0.5)] backdrop-blur-sm">
      <h1 className="font-title text-4xl text-[#173642]">{t('authTitleRegister')}</h1>
      <p className="mt-2 text-sm text-[#173642]/70">Crea una cuenta para empezar a organizar tus declaraciones.</p>

      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <label className="block text-sm font-semibold text-[#173642]">
          {t('authFullName')}
          <input
            className="mt-1 w-full rounded-xl border border-[#173642]/20 bg-white px-3 py-2 outline-none ring-[#24513f] transition focus:ring-2"
            type="text"
            autoComplete="name"
            required
            maxLength={200}
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </label>

        <label className="block text-sm font-semibold text-[#173642]">
          {t('authEmail')}
          <input
            className="mt-1 w-full rounded-xl border border-[#173642]/20 bg-white px-3 py-2 outline-none ring-[#24513f] transition focus:ring-2"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label className="block text-sm font-semibold text-[#173642]">
          {t('authPassword')}
          <input
            className="mt-1 w-full rounded-xl border border-[#173642]/20 bg-white px-3 py-2 outline-none ring-[#24513f] transition focus:ring-2"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        {error ? <p className="rounded-lg bg-red-100 px-3 py-2 text-sm text-red-700">{error}</p> : null}

        <button
          type="submit"
          className="w-full rounded-xl bg-[#24513f] px-4 py-3 font-semibold text-white transition hover:bg-[#173642] disabled:opacity-60"
          disabled={loading}
        >
          {loading ? 'Creando cuenta...' : t('authSubmitRegister')}
        </button>
      </form>

      <p className="mt-6 text-sm text-[#173642]/75">
        <Link to="/login" className="font-semibold text-[#24513f] hover:underline">
          {t('authToLogin')}
        </Link>
      </p>
    </section>
  )
}
