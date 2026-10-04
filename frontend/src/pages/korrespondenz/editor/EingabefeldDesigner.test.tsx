import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EingabefeldDesigner } from './EingabefeldDesigner'
import type { Eingabefeld } from '../../../types'

function Huelle({ start, onChange }: { start: Eingabefeld[]; onChange?: (f: Eingabefeld[]) => void }) {
  const [felder, setFelder] = useState(start)
  return <EingabefeldDesigner felder={felder} onChange={f => { setFelder(f); onChange?.(f) }} />
}

describe('EingabefeldDesigner', () => {
  it('legt ein Feld mit Name, Label, Typ und Pflicht an', async () => {
    const onChange = vi.fn()
    render(<Huelle start={[]} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: '+ Feld' }))

    await userEvent.type(screen.getByLabelText('Feldname 1'), 'versammlung_ort')
    await userEvent.type(screen.getByLabelText('Label 1'), 'Ort')
    await userEvent.selectOptions(screen.getByLabelText('Typ 1'), 'mehrzeilig')
    await userEvent.click(screen.getByRole('checkbox'))

    expect(onChange).toHaveBeenLastCalledWith([
      { name: 'versammlung_ort', label: 'Ort', typ: 'mehrzeilig', pflicht: true },
    ])
  })

  it('bietet genau die sieben Feldtypen der Spec an', () => {
    render(<Huelle start={[{ name: 'a', label: 'A', typ: 'text', pflicht: false }]} />)
    const werte = Array.from((screen.getByLabelText('Typ 1') as HTMLSelectElement).options).map(o => o.value)
    expect(werte).toEqual(['text', 'mehrzeilig', 'datum', 'uhrzeit', 'betrag', 'liste', 'ja_nein'])
  })

  it('warnt bei ungültigem und doppeltem Namen', () => {
    render(<Huelle start={[
      { name: 'Falsch Name', label: '', typ: 'text', pflicht: false },
      { name: 'ok', label: '', typ: 'text', pflicht: false },
      { name: 'ok', label: '', typ: 'text', pflicht: false },
    ]} />)
    expect(screen.getByText(/Nur a–z, 0–9 und _/)).toBeInTheDocument()
    expect(screen.getAllByText('Name doppelt vergeben.')).toHaveLength(2)
  })

  it('entfernt ein Feld', async () => {
    const onChange = vi.fn()
    render(<Huelle start={[{ name: 'a', label: 'A', typ: 'text', pflicht: false }]} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'Feld 1 entfernen' }))
    expect(onChange).toHaveBeenLastCalledWith([])
    expect(screen.getByText('Keine Eingabefelder definiert.')).toBeInTheDocument()
  })

  it('ist im Lesemodus nicht editierbar', () => {
    render(<EingabefeldDesigner readOnly onChange={() => {}}
      felder={[{ name: 'a', label: 'A', typ: 'text', pflicht: false }]} />)
    expect(screen.queryByRole('button', { name: '+ Feld' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Feldname 1')).toBeDisabled()
  })
})
