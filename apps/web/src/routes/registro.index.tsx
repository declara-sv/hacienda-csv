import { createFileRoute } from '@tanstack/react-router'

// Bare /registro. Without it the splat child would match /registro too, and
// the router warns that links to /registro resolve to /registro/$.
export const Route = createFileRoute('/registro/')({ component: () => null })
