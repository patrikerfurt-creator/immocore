import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PlatzhalterSeitenleiste } from './PlatzhalterSeitenleiste'
import type { Platzhalter } from '../../../types'

const PLATZHALTER: Platzhalter[] = [
  { name: 'empfaenger.briefanrede', beschreibung: 'Briefanrede', typ: 'text', beispiel: 'Sehr geehrter Herr Muster', gruppe: 'empfaenger' },
  { name: 'empfaenger.name', beschreibung: 'Name des Empfängers', typ: 'text', beispiel: 'Max Muster', gruppe: 'empfaenger' },
  { name: 'mahnung.frist', beschreibung: 'Zahlungsfrist', typ: 'datum', beispiel: '13.10.2026', gruppe: 'mahnung' },
]

describe('PlatzhalterSeitenleiste', () => {
  it('gruppiert die Platzhalter und fügt per Klick den vollen Namen ein', async () => {
    const onEinfuegen = vi.fn()
    render(<PlatzhalterSeitenleiste platzhalter={PLATZHALTER} onEinfuegen={onEinfuegen} />)

    expect(screen.getByText('Empfänger')).toBeInTheDocument()
    expect(screen.getByText('Mahnung')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'frist' }))
    expect(onEinfuegen).toHaveBeenCalledWith('mahnung.frist')
  })

  it('filtert per Suche nach Name und Beschreibung', async () => {
    render(<PlatzhalterSeitenleiste platzhalter={PLATZHALTER} onEinfuegen={() => {}} />)
    await userEvent.type(screen.getByLabelText('Platzhalter suchen'), 'zahlungsfrist')
    expect(screen.getByRole('button', { name: 'frist' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'briefanrede' })).not.toBeInTheDocument()
  })

  it('zeigt Ladezustand und Fehler und sperrt im Lesemodus', () => {
    const { rerender } = render(<PlatzhalterSeitenleiste platzhalter={[]} laedt onEinfuegen={() => {}} />)
    expect(screen.getByText('Lade Platzhalter…')).toBeInTheDocument()
    rerender(<PlatzhalterSeitenleiste platzhalter={[]} fehler="kaputt" onEinfuegen={() => {}} />)
    expect(screen.getByText('kaputt')).toBeInTheDocument()
    rerender(<PlatzhalterSeitenleiste platzhalter={PLATZHALTER} readOnly onEinfuegen={() => {}} />)
    expect(screen.getByRole('button', { name: 'frist' })).toBeDisabled()
  })
})
