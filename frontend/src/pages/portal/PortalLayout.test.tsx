import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PortalLayout } from './PortalLayout'
import { sepaMandatStatus } from '../../api/portal'
import type { SepaMandatStatus } from '../../api/portal'

vi.mock('../../api/portal', async () => {
  const echt = await vi.importActual<typeof import('../../api/portal')>('../../api/portal')
  return { ...echt, sepaMandatStatus: vi.fn() }
})

function status(teil: Partial<SepaMandatStatus>): SepaMandatStatus {
  return {
    kann_erteilen: true, hinderungsgrund: null, empfaenger_email_maskiert: 'm***@example.de',
    kopfzeile_aktion: 'erteilen', auswahl_noetig: false, offene_anfrage: null,
    geltungsbereiche: [{ schluessel: 'alle', ev_id: null, bezeichnung: 'Alle Einheiten', aktion: 'erteilen', mandat: null }],
    ...teil,
  }
}

function rendere() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/portal/daten']}>
        <Routes>
          <Route path="/portal" element={<PortalLayout />}>
            <Route path="daten" element={<div>Inhalt</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.setItem('portal_token', 'abc')
})

describe('PortalLayout SEPA-Button', () => {
  it('zeigt "… ändern", wenn bereits ein Mandat besteht', async () => {
    vi.mocked(sepaMandatStatus).mockResolvedValue(status({ kopfzeile_aktion: 'aendern' }))
    rendere()
    expect(await screen.findByRole('button', { name: 'SEPA-Lastschriftmandat ändern' })).toBeInTheDocument()
  })

  it('zeigt das neutrale Label beim Laden und bei "erteilen"', async () => {
    vi.mocked(sepaMandatStatus).mockResolvedValue(status({}))
    rendere()
    expect(screen.getByRole('button', { name: 'SEPA-Lastschriftmandat' })).toBeInTheDocument()
    expect(await screen.findByText('Inhalt')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'SEPA-Lastschriftmandat' })).toBeInTheDocument()
  })

  it('rendert den Button auch bei Query-Fehler', async () => {
    vi.mocked(sepaMandatStatus).mockRejectedValue(new Error('boom'))
    rendere()
    expect(await screen.findByRole('button', { name: 'SEPA-Lastschriftmandat' })).toBeInTheDocument()
  })

  it('öffnet den Dialog per Klick', async () => {
    vi.mocked(sepaMandatStatus).mockResolvedValue(status({}))
    const user = userEvent.setup()
    rendere()
    await user.click(await screen.findByRole('button', { name: 'SEPA-Lastschriftmandat' }))
    expect(await screen.findByRole('dialog', { name: 'SEPA-Lastschriftmandat erteilen' })).toBeInTheDocument()
  })
})
