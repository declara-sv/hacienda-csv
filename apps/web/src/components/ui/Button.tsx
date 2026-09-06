import { Loader2 } from 'lucide-react'
import { cn } from '#/lib/cn'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
export type ButtonSize = 'md' | 'sm'

const base =
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control font-semibold transition duration-200 ease-out-expo active:translate-y-px disabled:pointer-events-none disabled:opacity-60'

const variants: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-accent-ink hover:bg-accent-hover',
  secondary:
    'border border-line-strong bg-surface-raised text-ink hover:border-accent hover:text-accent',
  ghost: 'text-ink hover:bg-accent-soft',
}

const sizes: Record<ButtonSize, string> = {
  md: 'h-10 px-4 text-sm',
  sm: 'h-8 px-3 text-sm',
}

export function buttonClasses(
  variant: ButtonVariant = 'primary',
  size: ButtonSize = 'md',
  className?: string,
) {
  return cn(base, variants[variant], sizes[size], className)
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  loadingLabel?: string
  icon?: ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  loadingLabel,
  icon,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" aria-hidden />
      ) : icon ? (
        <span className="-ml-0.5 inline-flex" aria-hidden>
          {icon}
        </span>
      ) : null}
      {loading && loadingLabel ? loadingLabel : children}
    </button>
  )
}
