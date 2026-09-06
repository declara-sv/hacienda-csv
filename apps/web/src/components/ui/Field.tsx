import { ChevronDown } from 'lucide-react'
import { cn } from '#/lib/cn'
import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'

/*
  Form pattern: label above, control, hint or error below, gap-2.
  Placeholders are never used as labels.
*/

type FieldProps = {
  id: string
  label: string
  hint?: string
  error?: string | null
  className?: string
  children: ReactNode
}

export function fieldDescribedBy(
  id: string,
  hint?: string,
  error?: string | null,
) {
  if (error) return `${id}-error`
  if (hint) return `${id}-hint`
  return undefined
}

export function Field({
  id,
  label,
  hint,
  error,
  className,
  children,
}: FieldProps) {
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <label htmlFor={id} className="text-sm font-semibold text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export const controlClass =
  'w-full rounded-control border border-line-strong bg-surface-raised px-3 text-base text-ink transition duration-200 placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:opacity-60 aria-[invalid=true]:border-danger'

type InputProps = InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }

export function Input({ className, invalid, ...rest }: InputProps) {
  return (
    <input
      className={cn(controlClass, 'h-10', className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean
}

export function Select({ className, invalid, children, ...rest }: SelectProps) {
  return (
    <div className="relative">
      <select
        className={cn(controlClass, 'h-10 appearance-none pr-9', className)}
        aria-invalid={invalid || undefined}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted"
        strokeWidth={2}
        aria-hidden
      />
    </div>
  )
}

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  invalid?: boolean
}

export function Textarea({ className, invalid, ...rest }: TextareaProps) {
  return (
    <textarea
      className={cn(controlClass, 'min-h-28 py-2', className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
}
