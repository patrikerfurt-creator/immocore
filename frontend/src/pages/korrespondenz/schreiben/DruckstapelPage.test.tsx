import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DruckstapelPage, offeneStapel } from './DruckstapelPage'
import { druckstapelApi, schreibenApi } from '../../../api/korrespondenz'
import { objekteApi } from '../../../api/objekte'
import type { Druckstapel } from '../../../types'
import { schreibenMuster } from './testDaten'


vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return {
    ...echt,
    schreibenApi: { list: vi.fn() },
    druckstapelApi: { erzeugen: vi.fn(), bestaetigen: vi.fn(), pdf: vi.fn() },
  }
})
vi.mock('../../../api/objekte', () => ({ objekteApi: { list: vi.fn() } }))

const liste = vi.mocked(schreibenApi.list)
const erzeugen = vi.mocked(druckstapelApi.erzeugen)
const bestaetigen = vi.mocked(druckstapelApi.bestaetigen)

const BRIEF_1 = schreibenMuster({ id: 's1', nummer: 'KS-2026-000001', status: 'freigegeben', dokument: 'd1' })
const BRIEF_2 = schreibenMuster({
  id: 's2', nummer: 'KS-2026-000002', status: 'freigegeben', dokument: 'd2', empfaenger: { id: 'p2', name: 'Erika Beispiel' },
})

const STAPEL: Druckstapel = {
  id: 'abcdef12-0000-0000-0000-000000000000', status: 'offen', status_anzeige: 'Offen', dokument: 'sammel1', anzahl: 2,
  schreiben: [
    { id: 's1', nummer: 'KS-2026-000001', status: 'freigegeben' },
    { id: 's2', nummer: 'KS-2026-000002', status: 'freigegeben' },
  ],
  erstellt_am: '2026-09-29T08:00:00Z', erstellt_von: 1, bestaetigt_am: null, bestaetigt_von: null,
}

function rendere() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter><DruckstapelPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(objekteApi.list).mockResolvedValue([{ id: 'o1', objektnummer: '1001', bezeichnung: 'Musterstraße 1' } as never])
  liste.mockImplementation(async params => (params?.druckbereit ? [BRIEF_1, BRIEF_2] : []))
  vi.mocked(druckstapelApi.pdf).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  URL.createObjectURL = vi.fn(() => 'blob:sammel-1')
  URL.revokeObjectURL = vi.fn()
})

describe('offeneStapel', () => {
  it('gruppiert Briefe nach Stapel und ergänzt die gemerkte Dokument-Id', () => {
    const ergebnis = offeneStapel(
      [
        schreibenMuster({ id: 'a', nummer: 'N1', druckstapel: 'st1' }),
        schreibenMuster({ id: 'b', nummer: 'N2', druckstapel: 'st1' }),
        schreibenMuster({ id: 'c', nummer: 'N3', druckstapel: null }),
      ],
      [],
      { st1: 'dok9' },
    )
    expect(ergebnis).toEqual([{ id: 'st1', nummern: ['N1', 'N2'], dokument: 'dok9' }])
  })
})

describe('DruckstapelPage', () => {
  it('zeigt die druckbereiten Briefe', async () => {
    rendere()
    expect(await screen.findByText('Max Muster')).toBeInTheDocument()
    expect(screen.getByText('Erika Beispiel')).toBeInTheDocument()
    expect(liste).toHaveBeenCalledWith({ druckbereit: '1' })
    expect(screen.getByRole('button', { name: 'Sammel-PDF erzeugen (2)' })).toBeEnabled()
  })

  it('erzeugt das Sammel-PDF (alle Briefe), zeigt es als Blob und bestätigt „gedruckt und kuvertiert“', async () => {
    erzeugen.mockResolvedValue(STAPEL)
    bestaetigen.mockResolvedValue({ ...STAPEL, status: 'bestaetigt' })
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Sammel-PDF erzeugen (2)' }))

    expect(erzeugen).toHaveBeenCalledWith({})
    expect(await screen.findByText('Druckstapel mit 2 Briefen erzeugt.')).toBeInTheDocument()
    const karte = await screen.findByTestId('stapel')
    expect(localStorage.getItem('korrespondenz-druckstapel-dokumente')).toContain('sammel1')

    await userEvent.click(within(karte).getByRole('button', { name: 'Sammel-PDF anzeigen' }))
    await waitFor(() => expect(screen.getByTitle('Sammel-PDF')).toHaveAttribute('src', 'blob:sammel-1'))
    expect(druckstapelApi.pdf).toHaveBeenCalledWith('sammel1')

    await userEvent.click(within(karte).getByRole('button', { name: 'Gedruckt und kuvertiert bestätigen' }))
    expect(bestaetigen).not.toHaveBeenCalled()
    await userEvent.click(within(karte).getByRole('button', { name: 'Ja, gedruckt und kuvertiert' }))

    expect(await screen.findByText(/Druckstapel bestätigt: 2 Briefe/)).toBeInTheDocument()
    expect(bestaetigen).toHaveBeenCalledWith(STAPEL.id)
    await waitFor(() => expect(screen.queryByTestId('stapel')).not.toBeInTheDocument())
    expect(localStorage.getItem('korrespondenz-druckstapel-dokumente')).not.toContain('sammel1')
  })

  it('bündelt nur die angehakten Briefe', async () => {
    erzeugen.mockResolvedValue({ ...STAPEL, anzahl: 1, schreiben: [STAPEL.schreiben[0]] })
    rendere()
    await userEvent.click(await screen.findByRole('checkbox', { name: 'KS-2026-000002 auswählen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Sammel-PDF erzeugen (1)' }))
    expect(erzeugen).toHaveBeenCalledWith({ schreiben_ids: ['s2'] })
  })

  it('filtert auf ein Objekt und reicht es an das Erzeugen weiter', async () => {
    erzeugen.mockResolvedValue(STAPEL)
    rendere()
    await screen.findByText('Max Muster')
    await userEvent.selectOptions(screen.getByLabelText('Objekt'), 'o1')
    await waitFor(() => expect(liste).toHaveBeenCalledWith({ druckbereit: '1', objekt: 'o1' }))
    await userEvent.click(screen.getByRole('button', { name: /Sammel-PDF erzeugen/ }))
    expect(erzeugen).toHaveBeenCalledWith({ objekt: 'o1' })
  })

  it('zeigt eine Backend-Fehlermeldung beim Erzeugen', async () => {
    erzeugen.mockRejectedValue(new Error('boom'))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: /Sammel-PDF erzeugen/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Druckstapel konnte nicht erzeugt werden.')
  })

  it('findet offene Stapel nach dem Neuladen über die Briefe und das gemerkte Dokument', async () => {
    localStorage.setItem('korrespondenz-druckstapel-dokumente', JSON.stringify({ st1: 'sammel9' }))
    liste.mockImplementation(async params => (params?.druckbereit ? [] : [
      schreibenMuster({ id: 'a', nummer: 'KS-2026-000007', status: 'freigegeben', druckstapel: 'st1' }),
    ]))
    rendere()
    const karte = await screen.findByTestId('stapel')
    expect(within(karte).getByText(/KS-2026-000007/)).toBeInTheDocument()
    expect(within(karte).getByRole('button', { name: 'Sammel-PDF anzeigen' })).toBeInTheDocument()
  })
})
