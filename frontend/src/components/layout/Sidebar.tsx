import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/useAuth'
import { useHasRole } from '@/hooks/useHasRole'

const dashboardNavItems = [
  { label: 'Activos / Pasivos', to: '/dashboard/balance-sheet' },
  { label: 'Ingresos / Gastos', to: '/dashboard/income-expenses' },
  { label: 'Estado de Resultado', to: '/dashboard/income-statement' },
  { label: 'Variación Patrimonial', to: '/dashboard/equity-variation' },
]

// Visible para contador + admin (Story 9.13 matriz autoritativa)
const contadorNavItems = [
  { label: 'Cargar Cartola', to: '/upload' },
  { label: 'Reconciliación', to: '/reconcile' },
]

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'flex items-center px-3 py-2 rounded-md text-sm transition-colors',
          isActive
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )
      }
    >
      {label}
    </NavLink>
  )
}

export function Sidebar() {
  const { isLoading } = useAuth()
  const canSeeContadorItems = useHasRole(['contador', 'admin'])

  if (isLoading) {
    return <aside className="w-56 flex-shrink-0 border-r bg-card" />
  }

  return (
    <aside className="w-56 flex-shrink-0 border-r bg-card flex flex-col">
      <div className="p-4 border-b">
        <span className="font-semibold text-sm text-foreground">EAG Family Office</span>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {dashboardNavItems.map((item) => (
          <NavItem key={item.to} to={item.to} label={item.label} />
        ))}

        {canSeeContadorItems && contadorNavItems.map((item) => (
          <NavItem key={item.to} to={item.to} label={item.label} />
        ))}
      </nav>
    </aside>
  )
}
