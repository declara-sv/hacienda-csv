import type { ClerkProvider } from '@clerk/tanstack-react-start'
import type { ComponentProps } from 'react'

type Appearance = NonNullable<
  ComponentProps<typeof ClerkProvider>['appearance']
>

const fontFamily = "'Source Sans 3', ui-sans-serif, system-ui, sans-serif"

/**
 * Clerk components read the app's design tokens (through the --auth-* aliases
 * in styles.css), so they follow light/dark mode with the rest of the UI. Clerk's styles live in the `clerk` CSS layer
 * (declared in styles.css) so Tailwind utilities in `elements` can override
 * them.
 */
export const clerkAppearance: Appearance = {
  cssLayerName: 'clerk',
  variables: {
    colorPrimary: 'var(--auth-accent)',
    colorPrimaryForeground: 'var(--auth-accent-ink)',
    colorBackground: 'var(--auth-surface-raised)',
    colorForeground: 'var(--auth-ink)',
    colorMutedForeground: 'var(--auth-ink-muted)',
    colorMuted: 'var(--auth-surface-sunken)',
    colorNeutral: 'var(--auth-ink)',
    colorInput: 'var(--auth-surface-raised)',
    colorInputForeground: 'var(--auth-ink)',
    colorBorder: 'var(--auth-line-strong)',
    colorRing: 'var(--auth-accent)',
    colorDanger: 'var(--auth-danger)',
    colorSuccess: 'var(--auth-success)',
    colorWarning: 'var(--auth-warning)',
    borderRadius: '0.5rem',
    fontFamily,
    fontFamilyButtons: fontFamily,
  },
}

/** Lets <SignIn>/<SignUp> fill the AuthLayout column instead of floating. */
export const authCardAppearance: Appearance = {
  elements: {
    rootBox: 'w-full',
    cardBox:
      'w-full max-w-none rounded-container border border-line shadow-none',
    card: 'shadow-none',
  },
}
