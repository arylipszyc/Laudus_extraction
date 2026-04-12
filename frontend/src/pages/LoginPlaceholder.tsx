import { Button } from '@/components/ui/button'

// Stub — Story 1.3 replaces this with real Google OAuth flow
export function LoginPlaceholder() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4">
        <h1 className="text-2xl font-semibold">EAG Family Office</h1>
        <p className="text-muted-foreground text-sm">Acceso restringido — implementación en Story 1.3</p>
        <Button disabled>Iniciar sesión con Google</Button>
      </div>
    </div>
  )
}
