import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { FilterProvider } from '@/contexts/FilterContext'
import { EntityFilter } from '@/components/filters/EntityFilter'
import { DateRangeFilter } from '@/components/filters/DateRangeFilter'

export function DashboardLayout() {
  // En la vista de reportes ocultamos los filtros de entidad/período (no aplican)
  // y la barra de sync mensual del header (ver Header minimal).
  const minimal = useLocation().pathname.startsWith('/reportes')
  return (
    <FilterProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-col flex-1 overflow-hidden">
          <Header minimal={minimal} />
          {!minimal && (
            <div className="flex items-center gap-4 px-6 py-3 border-b bg-card flex-shrink-0">
              <EntityFilter />
              <DateRangeFilter />
            </div>
          )}
          <main className="flex-1 overflow-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </FilterProvider>
  )
}
