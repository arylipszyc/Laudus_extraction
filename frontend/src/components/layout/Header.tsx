import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { logout } from '@/services/auth'
import { useSyncStatus } from '@/hooks'

export function Header() {
  const navigate = useNavigate()
  const { data: syncStatus } = useSyncStatus()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className="h-14 border-b bg-card flex items-center justify-between px-6 flex-shrink-0">
      <div className="text-sm text-muted-foreground">
        {/* Entity + date filter will go here in Story 3.2 */}
        Dashboard financiero
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {syncStatus?.job_status === 'running' && (
            <span className="text-blue-500">Sincronizando…</span>
          )}
          {syncStatus?.job_status === 'failed' && (
            <span className="text-destructive" title={syncStatus.error ?? undefined}>
              Error en sync
            </span>
          )}
          {syncStatus?.job_status !== 'running' &&
            syncStatus?.job_status !== 'failed' &&
            syncStatus?.balance_sheet?.last_sync && (
              <span>
                Sync:{' '}
                {new Date(syncStatus.balance_sheet.last_sync).toLocaleDateString('es-CL')}
              </span>
            )}
        </span>
        <Button variant="outline" size="sm" onClick={handleLogout}>
          Cerrar sesión
        </Button>
      </div>
    </header>
  )
}
