import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Login } from '@/pages/Login'
import { DashboardPlaceholder } from '@/pages/DashboardPlaceholder'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/hooks/useAuth'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { data: user, isLoading } = useAuth()
  if (isLoading) return <Skeleton className="h-screen w-screen" />
  if (!user) return <Navigate to="/login" replace />
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
          <Route path="balance-sheet" element={<DashboardPlaceholder />} />
          <Route path="income-expenses" element={<DashboardPlaceholder />} />
          <Route path="income-statement" element={<DashboardPlaceholder />} />
          <Route path="equity-variation" element={<DashboardPlaceholder />} />
        </Route>
        {/* Catch-all: redirect to login (Story 1.3 wires real auth) */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
