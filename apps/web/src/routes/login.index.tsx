import { createFileRoute } from '@tanstack/react-router'

// Bare /login. Without it the splat child would match /login too, and the
// router warns that links to /login resolve to /login/$.
export const Route = createFileRoute('/login/')({ component: () => null })
