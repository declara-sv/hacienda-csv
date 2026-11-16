import { createFileRoute } from '@tanstack/react-router'

// Sub-steps of Clerk's sign-in flow; the parent /login route renders <SignIn />.
export const Route = createFileRoute('/login/$')({ component: () => null })
