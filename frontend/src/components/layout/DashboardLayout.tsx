import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { FilterProvider } from '@/contexts/FilterContext'
import { EntityFilter } from '@/components/filters/EntityFilter'
import { DateRangeFilter } from '@/components/filters/DateRangeFilter'

export function DashboardLayout() {
  return (
    <FilterProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-col flex-1 overflow-hidden">
          <Header />
          <div className="flex items-center gap-4 px-6 py-3 border-b bg-card flex-shrink-0">
            <EntityFilter />
            <DateRangeFilter />
          </div>
          <main className="flex-1 overflow-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </FilterProvider>
  )
}
