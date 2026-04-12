import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

// Stub — Story 3 replaces this with real dashboard views
export function DashboardPlaceholder() {
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Dashboard</h2>
      <Card>
        <CardHeader>
          <CardTitle>Estado del sistema</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm">
            Dashboards financieros — implementación en Epic 3
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
