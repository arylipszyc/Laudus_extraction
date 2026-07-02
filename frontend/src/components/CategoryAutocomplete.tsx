import { useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listAccounts } from '@/services/accounts'

/**
 * Autocompletado de cuenta de categoría (plan `Expenses`). Input con dropdown filtrable +
 * navegación por teclado (↑/↓/Enter/Esc) y botón de limpiar; marca en ámbar una cuenta no
 * reconocida (se valida al guardar). La etiqueta y el texto de ayuda los pone el consumidor.
 * Extraído de ReconciliationPage (Story 6.4) para reusarlo en Categorización.
 */
export function CategoryAutocomplete({
  value,
  onChange,
  placeholder = 'Buscar cuenta… (ej. Expenses:EAG:Super)',
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts', 'Expenses'],
    queryFn: () => listAccounts('Expenses'),
  })
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const toggleOpen = () => {
    setActive(0)
    setOpen((o) => !o)
    inputRef.current?.focus()
  }

  const matches = useMemo(() => {
    const q = value.trim().toLowerCase()
    const list = q ? accounts.filter((a) => a.toLowerCase().includes(q)) : accounts
    return list.slice(0, 50)
  }, [accounts, value])

  const known = value.trim() === '' || accounts.includes(value.trim())

  const select = (a: string) => { onChange(a); setOpen(false) }

  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (!open) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, matches.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter' && matches[active]) { e.preventDefault(); select(matches[active]) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(0) }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          role="combobox" aria-expanded={open} aria-autocomplete="list"
          className={`w-full border rounded-md pl-3 pr-12 py-2 bg-background text-sm ${known ? '' : 'border-amber-400'}`}
        />
        <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center text-muted-foreground">
          {value && (
            <button type="button" aria-label="Limpiar"
              onMouseDown={(e) => { e.preventDefault(); onChange('') }}
              className="px-1 text-xs hover:text-foreground">✕</button>
          )}
          <button type="button" aria-label="Abrir lista"
            onMouseDown={(e) => { e.preventDefault(); toggleOpen() }}
            className="px-1 text-xs hover:text-foreground">▾</button>
        </div>
        {open && matches.length > 0 && (
          <ul role="listbox" className="absolute z-50 mt-1 w-full max-h-48 overflow-auto border rounded-md bg-card shadow text-sm">
            {matches.map((a, i) => (
              <li key={a} role="option" aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); select(a) }}
                onMouseEnter={() => setActive(i)}
                className={`px-3 py-1.5 cursor-pointer ${i === active ? 'bg-accent' : ''}`}>
                {a}
              </li>
            ))}
          </ul>
        )}
      </div>
      {!known && <p className="text-xs text-amber-600 mt-1">cuenta no reconocida — se validará al guardar</p>}
    </div>
  )
}
