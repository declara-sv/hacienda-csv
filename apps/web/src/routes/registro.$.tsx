import { createFileRoute } from '@tanstack/react-router'

// Sub-steps of Clerk's sign-up flow; the parent /registro route renders <SignUp />.
export const Route = createFileRoute('/registro/$')({ component: () => null })
