import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Login } from '@/pages/Login'
import { DashboardPlaceholder } from '@/pages/DashboardPlaceholder'
import { BalanceSheetPage } from '@/pages/BalanceSheetPage'
import { IncomeExpensesPage } from '@/pages/IncomeExpensesPage'
import { CartolaUploadPage } from '@/pages/CartolaUploadPage'
import { ReportesPage } from '@/pages/ReportesPage'
import { CuentasPendientesPage } from '@/pages/CuentasPendientesPage'
import { ReconciliationPage } from '@/pages/ReconciliationPage'
import { TcReconciliationPage } from '@/pages/TcReconciliationPage'
import { CategorizacionPage } from '@/pages/CategorizacionPage'
import { CommentsInboxPage } from '@/pages/CommentsInboxPage'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { useHasRole } from '@/hooks/useHasRole'
import { ServerUnavailableError } from '@/services/auth'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { data: user, isLoading, error, refetch } = useAuth()
  if (isLoading) return <Skeleton className="h-screen w-screen" />
  // Backend arrancando (cold start) → esperar, NO botar al login (fix 6a Fase 1).
  if (error instanceof ServerUnavailableError) {
    return (
      <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 p-6 text-center">
        <h1 className="text-xl font-semibold">El servidor está arrancando…</h1>
        <p className="text-sm text-muted-foreground">
          Esto puede tardar unos segundos. Reintentando automáticamente.
        </p>
        <Button onClick={() => refetch()}>Reintentar</Button>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequireContador({ children }: { children: React.ReactNode }) {
  const allowed = useHasRole(['contador', 'admin'])
  if (!allowed) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard/*"
          element={
            <RequireAuth>
              <DashboardLayout />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPlaceholder />} />
          <Route path="balance-sheet" element={<BalanceSheetPage />} />
          <Route path="income-expenses" element={<IncomeExpensesPage />} />
          <Route path="income-statement" element={<DashboardPlaceholder />} />
          <Route path="equity-variation" element={<DashboardPlaceholder />} />
        </Route>
        <Route
          path="/upload"
          element={
            <RequireAuth>
              <RequireContador>
                <DashboardLayout />
              </RequireContador>
            </RequireAuth>
          }
        >
          <Route index element={<CartolaUploadPage />} />
        </Route>
        <Route
          path="/reportes"
          element={
            <RequireAuth>
              <RequireContador>
                <DashboardLayout />
              </RequireContador>
            </RequireAuth>
          }
        >
          <Route index element={<ReportesPage />} />
        </Route>
        <Route
          path="/cuentas-pendientes"
          element={
            <RequireAuth>
              <RequireContador>
                <DashboardLayout />
              </RequireContador>
            </RequireAuth>
          }
        >
          <Route index element={<CuentasPendientesPage />} />
        </Route>
        <Route
          path="/reconciliation"
          element={
            <RequireAuth>
              <RequireContador>
                <DashboardLayout />
              </RequireContador>
            </RequireAuth>
          }
        >
          <Route index element={<ReconciliationPage />} />
        </Route>
        <Route
          path="/cuadre-tc"
          element={
            <RequireAuth>
              <RequireContador>
                <DashboardLayout />
              </RequireContador>
            </RequireAuth>
          }
        >
          <Route index element={<TcReconciliationPage />} />
        </Route>
        <Route
          path="/categorizacion"
          element={
            <RequireAuth>
              <RequireContador>
                <DashboardLayout />
              </RequireContador>
            </RequireAuth>
          }
        >
          <Route index element={<CategorizacionPage />} />
        </Route>
        {/* Story 7.2 — inbox de comentarios: accesible para AMBOS roles (owner family + contador),
            por eso va bajo RequireAuth SIN RequireContador. */}
        <Route
          path="/comments"
          element={
            <RequireAuth>
              <DashboardLayout />
            </RequireAuth>
          }
        >
          <Route index element={<CommentsInboxPage />} />
        </Route>
        {/* Catch-all: redirect to login (Story 1.3 wires real auth) */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
