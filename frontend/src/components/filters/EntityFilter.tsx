import { ENTITIES, useFilters, type Entity } from '@/contexts/FilterContext'

export function EntityFilter() {
  const { entity, setEntity } = useFilters()
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-muted-foreground whitespace-nowrap">Entidad:</label>
      <select
        value={entity}
        onChange={(e) => setEntity(e.target.value as Entity)}
        className="text-sm border rounded-md px-2 py-1 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
      >
        {ENTITIES.map((e) => (
          <option key={e} value={e}>{e}</option>
        ))}
      </select>
    </div>
  )
}
