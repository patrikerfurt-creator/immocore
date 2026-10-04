import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PersonDetail } from './PersonDetail'
import { personenApi } from '../../api/personen'
import { vorlagenApi } from '../../api/korrespondenz'


vi.mock('../../api/personen', () => ({
  personenApi: { get: vi.fn(), eigentumsverhaeltnisse: vi.fn(), list: vi.fn() },
}))
vi.mock('../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../api/korrespondenz')>('../../api/korrespondenz')
  return { ...echt, vorlagenApi: { list: vi.fn(), versionen: vi.fn() } }
})
vi.mock('./PersonForm', () => ({ PersonForm: () => <p>Formular</p> }))
vi.mock('./PortalZugangKarte', () => ({ PortalZugangKarte: () => null }))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(personenApi.get).mockResolvedValue({
    id: 'p1', personennummer: 'P-1', name: 'Max Muster', person_typ: '100', ibans: [], email: '', telefon: '',
  } as never)
  vi.mocked(personenApi.eigentumsverhaeltnisse).mockResolvedValue([])
  vi.mocked(vorlagenApi.list).mockResolvedValue([])
})

describe('PersonDetail — Schreiben erstellen', () => {
  it('öffnet den Dialog mit dem Empfänger der Person; im Bearbeitungsmodus ist der Button ausgeblendet', async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/personen/p1']}>
          <Routes><Route path="/personen/:id" element={<PersonDetail />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Schreiben erstellen' }))
    const dialog = screen.getByRole('dialog', { name: 'Schreiben erstellen' })
    expect(dialog).toHaveTextContent('Max Muster')

    await userEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Bearbeiten' }))
    expect(screen.queryByRole('button', { name: 'Schreiben erstellen' })).not.toBeInTheDocument()
  })
})
