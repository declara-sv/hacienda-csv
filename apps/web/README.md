# HaciendaCSV web

Frontend for HaciendaCSV, a filing tool for accountants in El Salvador. Built with TanStack Start, React 19, TanStack Query, and Tailwind CSS v4.

## Run locally

```bash
pnpm install
pnpm dev
```

The app runs on port 3000 and talks to the API at `VITE_API_URL` (defaults to `http://localhost:5184`, see `.env.example`).

## Scripts

```bash
pnpm dev      # start the dev server
pnpm build    # production build (Nitro SSR)
pnpm test     # vitest
pnpm lint     # eslint
pnpm check    # prettier --write and eslint --fix
```

## Structure

- `src/routes/` file-based routes. `/login`, `/registro`, `/clientes`, `/clientes/$clientId`, `/clientes/$clientId/periodos/$periodId/cargas`.
- `src/components/ui/` shared primitives: Button, Field (Input, Select, Textarea), Notice, StatusChip, Skeleton, EmptyState, Breadcrumb, PageHeader.
- `src/styles.css` design tokens. Light and dark values live as CSS variables and are mapped into Tailwind through `@theme inline`.
- `src/i18n/messages.ts` all visible copy (Spanish).
- `src/lib/api-client.ts` typed API client with token refresh.

## Design rules in short

- One accent (`--accent`, brand green). Neutrals come from the same warm family.
- Shape lock: controls 8px, containers 16px, nav links and status chips are pills.
- Fonts are self-hosted through Fontsource: Bitter for the wordmark and page titles, Source Sans 3 for everything else.
- Every async view has loading, empty, error, and success states.
- Motion is CSS only and collapses under `prefers-reduced-motion`.
