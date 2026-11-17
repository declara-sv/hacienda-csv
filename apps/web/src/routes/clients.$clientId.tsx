import { Outlet, createFileRoute } from '@tanstack/react-router'

// Layout for /clients/$clientId and its children. The detail page itself
// lives in clients.$clientId.index.tsx so that nested routes such as
// /clients/$clientId/periods/$periodId/uploads can render through the outlet.
export const Route = createFileRoute('/clients/$clientId')({
  component: Outlet,
})
