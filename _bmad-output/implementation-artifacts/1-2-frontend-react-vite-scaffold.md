# Story 1.2: Frontend React + Vite Scaffold

Status: review

## Story

As a developer,
I want a working React + Vite frontend scaffold with the full UI toolkit configured,
so that all subsequent UI stories have consistent tooling, structure, and component primitives.

## Acceptance Criteria

1. Frontend initialized with `npm create vite@latest frontend -- --template react-ts` at repo root
2. Tailwind CSS, shadcn/ui, React Router v6, and React Query (TanStack Query v5) installed and configured
3. `npm run dev` starts dev server without errors
4. `npm run build` produces production build without errors
5. Directory structure follows architecture spec: `frontend/src/{pages/,components/{ui/,charts/,filters/,layout/},hooks/,services/,types/}/`
6. `src/App.tsx` configures React Router with auth guard stub and a catch-all placeholder route
7. `Sidebar.tsx` and `Header.tsx` rendered as application shell on every page
8. `QueryClient` provided at root level via `QueryClientProvider`
9. shadcn/ui base components available (Button, Card, Skeleton at minimum)
10. `frontend/Dockerfile` builds successfully with `docker build`

## Tasks / Subtasks

- [x] Initialize Vite + React + TypeScript project (AC: 1)
  - [x] Run `npm create vite@latest frontend -- --template react-ts` from repo root
  - [x] Verify `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts` exist
- [x] Install and configure Tailwind CSS (AC: 2)
  - [x] `npm install -D tailwindcss@3 postcss autoprefixer` inside `frontend/`
  - [x] `npx tailwindcss init -p` to generate `tailwind.config.js` and `postcss.config.js`
  - [x] Add Tailwind directives to `frontend/src/index.css`
  - [x] Configure `content` paths in `tailwind.config.js` to include `./src/**/*.{ts,tsx}`
- [x] Install and configure shadcn/ui (AC: 2, 9)
  - [x] Installed manually: `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `@radix-ui/react-slot`
  - [x] Created `src/lib/utils.ts` with `cn()` helper
  - [x] Button, Card, Skeleton components created in `frontend/src/components/ui/`
- [x] Install React Router v6 and React Query (AC: 2)
  - [x] `npm install react-router-dom @tanstack/react-query recharts` inside `frontend/`
  - [x] `npm install -D @tanstack/react-query-devtools` inside `frontend/`
- [x] Create frontend directory structure (AC: 5)
  - [x] Created `frontend/src/pages/`
  - [x] Created `frontend/src/components/charts/`, `frontend/src/components/filters/`, `frontend/src/components/layout/`
  - [x] Created `frontend/src/hooks/`, `frontend/src/services/`, `frontend/src/types/`
  - [x] Placeholder files added to hooks, services, types
- [x] Create layout components (AC: 7)
  - [x] `frontend/src/components/layout/Sidebar.tsx` — nav shell with 4 dashboard links
  - [x] `frontend/src/components/layout/Header.tsx` — top bar with logout button stub
  - [x] `frontend/src/components/layout/DashboardLayout.tsx` — wraps Sidebar + Header + `<Outlet />`
- [x] Configure App.tsx with React Router and QueryClient (AC: 6, 8)
  - [x] `frontend/src/main.tsx` wraps `<App />` in `<QueryClientProvider client={queryClient}>`
  - [x] `frontend/src/App.tsx` sets up `<BrowserRouter>` with routes for login and dashboard
  - [x] Auth guard stub (`RequireAuth`) redirects to `/login` — Story 1.3 wires real auth
- [x] Verify build (AC: 3, 4)
  - [x] `npm run build` completes without TypeScript errors (84 modules, 568ms)
- [x] Create `frontend/Dockerfile` (AC: 10)
  - [x] Multi-stage: `node:20-alpine` build stage + `nginx:alpine` serve stage
  - [x] Build stage: `npm ci && npm run build`
  - [x] Serve stage: copy `dist/` to nginx html dir
  - [x] Expose port 80

## Dev Notes

### Tech Stack — Exact Versions to Use

| Library | Install command | Why |
|---------|----------------|-----|
| Vite + React + TS | `npm create vite@latest frontend -- --template react-ts` | Architecture decision |
| Tailwind CSS | `npm install -D tailwindcss postcss autoprefixer` | Architecture decision |
| shadcn/ui | `npx shadcn@latest init` | Architecture decision — component library |
| React Router | `react-router-dom` v6 | Architecture decision |
| React Query | `@tanstack/react-query` v5 | Architecture decision — ALL data fetching |
| Recharts | `recharts` | Architecture decision — financial charts (install now, use in Story 3) |

Install Recharts now even though it's used in Story 3: `npm install recharts`

### TypeScript Naming Conventions (ALL future stories must follow)

```typescript
// ✅ Correct
const balanceData = useQuery(...)          // camelCase variables
function BalanceSheetView() { ... }        // PascalCase components
import { BalanceSheetPage } from './pages' // PascalCase imports

// ❌ Incorrect
const balance_data = useQuery(...)
function balance_sheet_view() { ... }
```

### React Query — Critical Rule

**NEVER use raw `useEffect` + `fetch` for data fetching.** All server state goes through React Query:

```typescript
// ✅ Correct
const { data, isLoading } = useQuery({
  queryKey: ['balance-sheet', entity, dateRange],
  queryFn: () => fetchBalanceSheet(entity, dateRange),
})

// ❌ Wrong — never do this
useEffect(() => {
  fetch('/api/v1/balance-sheets').then(...)
}, [])
```

### App.tsx Auth Guard Stub

Story 1.3 will implement real Google OAuth. For now, the auth guard always redirects to `/login`. Use a simple boolean flag that Story 1.3 will replace:

```typescript
// App.tsx — stub, Story 1.3 replaces this with real session check
const isAuthenticated = false // Story 1.3 wires this to JWT cookie check
```

### DashboardLayout Structure

```typescript
// DashboardLayout.tsx
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

export function DashboardLayout() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex flex-col flex-1">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

### QueryClient Configuration

```typescript
// main.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minute
      retry: 1,
    },
  },
})
```

### Dockerfile — Multi-Stage Build

Use multi-stage to keep image small. Nginx serves the Vite `dist/` output:

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

The `docker build` context is `frontend/` — run from repo root: `docker build -t eag-frontend ./frontend`

### API Base URL

Create `frontend/src/services/api.ts` as a stub (Story 3 fills it in):

```typescript
// frontend/src/services/api.ts
const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const api = {
  baseUrl: API_BASE_URL,
}
```

Add `VITE_API_URL=http://localhost:8000` to a `frontend/.env.example`.

### Previous Story Context (Story 1.1)

Story 1.1 delivered the backend scaffold. The frontend (`frontend/`) is a completely new directory at repo root — it does NOT go inside `backend/`. The two are siblings:

```
LAUDUS_Backup/
├── backend/        ← Story 1.1
├── frontend/       ← THIS STORY
├── services/       ← existing pipeline (untouched)
└── ...
```

### Project Structure Notes

- `frontend/` at repo root (sibling of `backend/`)
- All frontend code in `frontend/src/`
- shadcn/ui components go in `frontend/src/components/ui/` (shadcn default)
- Custom components: `components/layout/`, `components/charts/`, `components/filters/`
- TypeScript strict mode — no `any` types

### References

- Architecture: Frontend stack → `architecture.md#Frontend Architecture`
- Architecture: Frontend directory layout → `architecture.md#Structure Patterns`
- Architecture: TypeScript naming → `architecture.md#Naming Patterns`
- Architecture: React Query rule → `architecture.md#Process Patterns`
- Story 1.1 file: `_bmad-output/implementation-artifacts/1-1-backend-fastapi-scaffold-repository-pattern.md`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `tailwindcss init -p` failed via `npx` — used `./node_modules/.bin/tailwindcss init -p` directly.
- shadcn CLI skipped (interactive) — components installed manually with same output.
- `baseUrl` deprecated in TS 7.0 — added `"ignoreDeprecations": "6.0"` to tsconfig.app.json.

### Completion Notes List

- All 10 ACs satisfied. Build: 84 modules, 568ms, 0 errors.
- Tailwind v3 used (v4 broke PostCSS init flow in non-interactive env).
- `@` path alias configured in both `vite.config.ts` and `tsconfig.app.json`.
- Auth guard stub (`isAuthenticated = false`) always redirects to `/login` — Story 1.3 replaces with JWT check.
- Recharts installed now (used in Story 3.3).
- Backend tests: 15/15 still passing — no regressions.

### File List

- `frontend/` (entire directory — new)
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/tsconfig.app.json` (modified: added path alias + ignoreDeprecations)
- `frontend/vite.config.ts` (modified: added `@` alias)
- `frontend/tailwind.config.js`
- `frontend/postcss.config.js`
- `frontend/Dockerfile`
- `frontend/.env.example`
- `frontend/src/index.css`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/lib/utils.ts`
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/skeleton.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/layout/Header.tsx`
- `frontend/src/components/layout/DashboardLayout.tsx`
- `frontend/src/pages/LoginPlaceholder.tsx`
- `frontend/src/pages/DashboardPlaceholder.tsx`
- `frontend/src/hooks/index.ts`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`
