import { createFileRoute } from '@tanstack/react-router'

// Sub-steps of Clerk's sign-up flow; the parent /signup route renders <SignUp />.
export const Route = createFileRoute('/signup/$')({ component: () => null })
