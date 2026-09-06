import { Outlet, createFileRoute } from '@tanstack/react-router'

// Layout for /clientes/$clientId and its children. The detail page itself
// lives in clientes.$clientId.index.tsx so that nested routes such as
// /clientes/$clientId/periodos/$periodId/cargas can render through the outlet.
export const Route = createFileRoute('/clientes/$clientId')({
  component: Outlet,
})
