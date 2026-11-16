import { X } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useI18n } from '#/i18n/I18nProvider'
import { cn } from '#/lib/cn'
import type { ReactNode } from 'react'

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

type DialogProps = {
  title: string
  description?: string
  onClose: () => void
  /** Blocks Escape and the close button, e.g. while a save is in flight. */
  closeDisabled?: boolean
  /** Element id to focus when the dialog opens; defaults to the first field. */
  initialFocusId?: string
  className?: string
  children: ReactNode
}

/**
 * Modal dialog. Mount it to open, unmount it to close: focus moves inside on
 * mount, stays trapped while open, and returns to the previously focused
 * element (the trigger) on unmount.
 */
export function Dialog({
  title,
  description,
  onClose,
  closeDisabled = false,
  initialFocusId,
  className,
  children,
}: DialogProps) {
  const { t } = useI18n()
  const titleId = useId()
  const descriptionId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const closeDisabledRef = useRef(closeDisabled)
  useEffect(() => {
    onCloseRef.current = onClose
    closeDisabledRef.current = closeDisabled
  })

  useEffect(() => {
    const returnFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
    const panel = panelRef.current
    const initial =
      (initialFocusId ? document.getElementById(initialFocusId) : null) ??
      panel?.querySelector<HTMLElement>(focusableSelector) ??
      panel
    initial?.focus({ preventScroll: true })

    return () => {
      if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true })
    }
    // Focus moves once per opening; later prop changes must not steal it.
  }, [])

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      if (!closeDisabledRef.current) onCloseRef.current()
      return
    }
    if (event.key !== 'Tab' || !panelRef.current) return
    const focusable = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(focusableSelector),
    )
    if (focusable.length === 0) {
      event.preventDefault()
      return
    }
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-6">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className={cn(
          'rise flex max-h-[92dvh] w-full max-w-3xl flex-col rounded-t-container border border-line bg-surface-raised shadow-raised focus:outline-none sm:rounded-container',
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0 space-y-1">
            <h2 id={titleId} className="text-lg font-semibold text-ink">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="text-sm text-ink-muted">
                {description}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={closeDisabled}
            aria-label={t('dialogClose')}
            className="-m-1 rounded-control p-1.5 text-ink-muted transition hover:bg-accent-soft hover:text-accent disabled:opacity-60"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
