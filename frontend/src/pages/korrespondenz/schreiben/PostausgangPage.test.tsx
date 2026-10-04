import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PostausgangPage } from './PostausgangPage'
import { schreibenApi } from '../../../api/korrespondenz'
import { mitarbeiterApi } from '../../../api/mitarbeiter'
import { objekteApi } from '../../../api/objekte'
import { schreibenMuster } from './testDaten'


vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return { ...echt, schreibenApi: { list: vi.fn() } }
})
vi.mock('../../../api/objekte', () => ({ objekteApi: { list: vi.fn() } }))
vi.mock('../../../api/mitarbeiter', () => ({ mitarbeiterApi: { list: vi.fn() } }))

const liste = vi.mocked(schreibenApi.list)

function rendere(pfad = '/korrespondenz/postausgang') {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}><PostausgangPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(objekteApi.list).mockResolvedValue([
    { id: 'o1', objektnummer: '1001', bezeichnung: 'Musterstraße 1' } as never,
  ])
  vi.mocked(mitarbeiterApi.list).mockResolvedValue([
    { id: 'm1', user_id: 7, vollname: 'Anna Betreuerin', aktiv: true } as never,
    { id: 'm2', user_id: 8, vollname: 'Ehemaliger', aktiv: false } as never,
  ])
  liste.mockResolvedValue([
    schreibenMuster(),
    schreibenMuster({
      id: 's2', nummer: 'KS-2026-000002', status: 'entwurf', nicht_erzeugbar: true, status_anzeige: 'Entwurf',
      fehler: 'Pflichtwert "einheit.flaeche" fehlt.', empfaenger: { id: 'p2', name: 'Erika Beispiel' }, betreff: '',
    }),
    schreibenMuster({
      id: 's3', nummer: 'KS-2026-000003', status: 'versand_fehlgeschlagen', kanal: 'email',
      fehler: 'Kein SMTP konfiguriert.', empfaenger: { id: 'p3', name: 'Paul Post' },
    }),
  ])
})

describe('PostausgangPage', () => {
  it('zeigt Schreiben zur Prüfung, nicht erzeugbare mit Ursache und fehlgeschlagene Sendungen', async () => {
    rendere()
    expect(await screen.findByText('Max Muster')).toBeInTheDocument()
    expect(screen.getByText('Erika Beispiel')).toBeInTheDocument()
    expect(screen.getAllByText('Nicht erzeugbar').length).toBeGreaterThan(0)
    const ursachen = screen.getAllByTestId('ursache').map(e => e.textContent)
    expect(ursachen).toContain('Ursache: Pflichtwert "einheit.flaeche" fehlt.')
    expect(ursachen).toContain('Ursache: Kein SMTP konfiguriert.')
    expect(screen.getByRole('link', { name: 'KS-2026-000001' })).toHaveAttribute('href', '/korrespondenz/postausgang/s1')
    // Standard-Ansicht: ohne status-Parameter (= Postausgang laut Backend)
    expect(liste).toHaveBeenCalledWith({})
  })

  it('gibt Ansicht, Objekt, Anlass und Betreuer als Filter ans Backend weiter', async () => {
    rendere()
    await screen.findByText('Max Muster')

    await userEvent.selectOptions(screen.getByLabelText('Ansicht'), 'nicht_erzeugbar')
    await userEvent.selectOptions(screen.getByLabelText('Objekt'), 'o1')
    await userEvent.selectOptions(screen.getByLabelText('Anlass'), 'etv_einladung')
    await userEvent.selectOptions(screen.getByLabelText('Betreuer'), '7')

    await waitFor(() => expect(liste).toHaveBeenLastCalledWith({
      status: 'nicht_erzeugbar', objekt: 'o1', anlass: 'etv_einladung', betreuer: '7',
    }))
    // nur aktive Mitarbeiter wählbar
    expect(screen.queryByRole('option', { name: 'Ehemaliger' })).not.toBeInTheDocument()
  })

  it('filtert auf einen Serienlauf, wenn ?serienlauf= übergeben wird', async () => {
    rendere('/korrespondenz/postausgang?serienlauf=lauf1&status=versand_fehlgeschlagen')
    await screen.findByText('Max Muster')
    expect(liste).toHaveBeenCalledWith({ status: 'versand_fehlgeschlagen', serienlauf: 'lauf1' })
  })

  it('zeigt einen Leerzustand', async () => {
    liste.mockResolvedValue([])
    rendere()
    expect(await screen.findByText('Keine Schreiben im Postausgang.')).toBeInTheDocument()
  })
})
