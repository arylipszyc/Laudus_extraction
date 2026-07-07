import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Boundary global — sin esto, una excepción de render deja pantalla blanca (fix 6b Fase 1). */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary atrapó una excepción de render:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 p-6 text-center">
          <h1 className="text-xl font-semibold">Algo salió mal</h1>
          <p className="text-sm text-muted-foreground">{this.state.error.message}</p>
          <Button onClick={() => window.location.reload()}>Recargar página</Button>
        </div>
      )
    }
    return this.props.children
  }
}
