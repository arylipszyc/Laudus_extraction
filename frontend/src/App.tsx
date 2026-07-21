// Base limpia (reset): scaffold vacío. El ledger es espejo de Laudus; la reportería
// se construye desde acá, capa por capa. Las vistas se definen en las próximas sesiones.
export default function App() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-50 text-slate-800">
      <h1 className="text-2xl font-semibold">LAUDUS — base limpia</h1>
      <p className="text-slate-500">
        Espejo de Laudus listo. La reportería se construye desde acá.
      </p>
    </main>
  )
}
