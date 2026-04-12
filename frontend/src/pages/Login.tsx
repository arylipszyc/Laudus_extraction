import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { api } from '@/services/api'

export function Login() {
  const [loading, setLoading] = useState(false)

  function handleLogin() {
    setLoading(true)
    window.location.href = `${api.baseUrl}/api/v1/auth/login`
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-6">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold">EAG Family Office</h1>
          <p className="text-muted-foreground text-sm">Acceso restringido — inicia sesión con tu cuenta Google autorizada</p>
        </div>
        <Button onClick={handleLogin} disabled={loading}>
          {loading ? 'Redirigiendo...' : 'Iniciar sesión con Google'}
        </Button>
      </div>
    </div>
  )
}
