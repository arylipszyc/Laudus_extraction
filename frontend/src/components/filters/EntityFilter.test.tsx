import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FilterProvider } from '@/contexts/FilterContext'
import { EntityFilter } from './EntityFilter'

describe('<EntityFilter /> entidades RUT2 (Story 11.2 AC2)', () => {
  it('renderiza las 7 entidades incluyendo FFCC y JAB, con EAG por defecto', () => {
    render(
      <FilterProvider>
        <EntityFilter />
      </FilterProvider>,
    )
    const select = screen.getByRole('combobox') as HTMLSelectElement
    const options = Array.from(select.options).map(o => o.value)
    expect(options).toEqual(['EAG', 'Jocelyn', 'Jeannette', 'Johanna', 'Jael', 'FFCC', 'JAB'])
    expect(select.value).toBe('EAG')
  })
})
