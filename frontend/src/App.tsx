import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Login } from '@/pages/Login'
import { DashboardPlaceholder } from '@/pages/DashboardPlaceholder'
import { BalanceSheetPage } from '@/pages/BalanceSheetPage'
import { IncomeExpensesPage } from '@/pages/IncomeExpensesPage'
import { CartolaUploadPage } from '@/pages/CartolaUploadPage'
import { ReportesPage } from '@/pages/ReportesPage'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/hooks/useAuth'
import { useHasRole } from '@/hooks/useHasRole'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { data: user, isLoading } = useAuth()
  if (isLoading) return <Skeleton className="h-screen w-screen" />
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
        {/* Catch-all: redirect to login (Story 1.3 wires real auth) */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
