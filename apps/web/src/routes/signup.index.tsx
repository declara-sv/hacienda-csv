import { createFileRoute } from '@tanstack/react-router'

// Bare /signup. Without it the splat child would match /signup too, and
// the router warns that links to /signup resolve to /signup/$.
export const Route = createFileRoute('/signup/')({ component: () => null })
