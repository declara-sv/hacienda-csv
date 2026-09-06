import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { useI18n } from '#/i18n/I18nProvider'
import { Input } from './Field'
import type { InputHTMLAttributes } from 'react'

type PasswordInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type'
> & {
  invalid?: boolean
}

export function PasswordInput({ className, ...rest }: PasswordInputProps) {
  const { t } = useI18n()
  const [visible, setVisible] = useState(false)

  return (
    <div className="relative">
      <Input
        type={visible ? 'text' : 'password'}
        className={`pr-11 ${className ?? ''}`}
        {...rest}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? t('authHidePassword') : t('authShowPassword')}
        aria-pressed={visible}
        className="absolute right-1.5 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-control text-ink-muted transition hover:bg-accent-soft hover:text-accent"
      >
        {visible ? (
          <EyeOff className="size-4" strokeWidth={2} aria-hidden />
        ) : (
          <Eye className="size-4" strokeWidth={2} aria-hidden />
        )}
      </button>
    </div>
  )
}
