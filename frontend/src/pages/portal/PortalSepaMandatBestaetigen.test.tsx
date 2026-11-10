import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { PortalSepaMandatBestaetigen } from './PortalSepaMandatBestaetigen'
import { sepaMandatBestaetigen, sepaMandatVorschau } from '../../api/portal'
import type { SepaMandatVorschau } from '../../api/portal'

vi.mock('../../api/portal', async () => {
  const echt = await vi.importActual<typeof import('../../api/portal')>('../../api/portal')
  return { ...echt, sepaMandatVorschau: vi.fn(), sepaMandatBestaetigen: vi.fn() }
})

const VORSCHAU: SepaMandatVorschau = {
  mandatstext: 'Ich ermächtige die Verwaltung, Zahlungen einzuziehen.',
  mandatsreferenz: 'PORTAL-100234-001', iban_maskiert: 'DE89 **** 3000', bic: 'COBADEFFXXX',
  geltungsbereich: 'alle', geltungsbereich_text: 'Alle Ihre Einheiten', aktion: 'erteilen',
  kontoinhaber_name: 'Max Muster', gueltig_bis: '2026-11-05T10:00:00Z',
}

function rendere() {
  render(
    <MemoryRouter initialEntries={['/portal/sepa-mandat/bestaetigen/tok123']}>
      <Routes>
        <Route path="/portal/sepa-mandat/bestaetigen/:token" element={<PortalSepaMandatBestaetigen />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(sepaMandatVorschau).mockResolvedValue(VORSCHAU)
  vi.mocked(sepaMandatBestaetigen).mockResolvedValue({
    detail: 'Ihr Mandat wurde erteilt.', mandatsreferenz: 'PORTAL-100234-001',
    geltungsbereich_text: 'Alle Ihre Einheiten', aktion: 'erteilen',
  })
})

describe('PortalSepaMandatBestaetigen', () => {
  it('holt beim Laden nur die Vorschau und bestätigt nicht automatisch', async () => {
    rendere()
    expect(await screen.findByText('Ich ermächtige die Verwaltung, Zahlungen einzuziehen.')).toBeInTheDocument()
    expect(sepaMandatVorschau).toHaveBeenCalledTimes(1)
    expect(sepaMandatVorschau).toHaveBeenCalledWith('tok123')
    expect(sepaMandatBestaetigen).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: 'SEPA-Lastschriftmandat erteilen' })).toBeInTheDocument()
    expect(screen.getByText('Max Muster')).toBeInTheDocument()
    expect(screen.getByText('PORTAL-100234-001')).toBeInTheDocument()
  })

  it('hält den Button ohne Checkbox deaktiviert', async () => {
    const user = userEvent.setup()
    rendere()
    const button = await screen.findByRole('button', { name: 'Mandat verbindlich erteilen' })
    expect(button).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    expect(button).toBeEnabled()
    await user.click(screen.getByRole('checkbox'))
    expect(button).toBeDisabled()
  })

  it('bestätigt mit gesetzter Checkbox und zeigt den Erfolg', async () => {
    const user = userEvent.setup()
    rendere()
    await user.click(await screen.findByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Mandat verbindlich erteilen' }))
    await waitFor(() => expect(sepaMandatBestaetigen).toHaveBeenCalledWith('tok123', true))
    expect(await screen.findByText('Ihr Mandat wurde erteilt.')).toBeInTheDocument()
    expect(screen.getByText(/Eine Kopie des Mandats/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Zur Anmeldung' })).toBeInTheDocument()
  })

  it('bleibt bei einem Fehler der Bestätigung auf der Seite', async () => {
    vi.mocked(sepaMandatBestaetigen).mockRejectedValue({ response: { data: { detail: 'Link bereits verwendet.' } } })
    const user = userEvent.setup()
    rendere()
    await user.click(await screen.findByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Mandat verbindlich erteilen' }))
    expect(await screen.findByText('Link bereits verwendet.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mandat verbindlich erteilen' })).toBeInTheDocument()
  })

  it('zeigt bei fehlgeschlagener Vorschau die Fehlermeldung', async () => {
    vi.mocked(sepaMandatVorschau).mockRejectedValue({ response: { status: 400 } })
    rendere()
    expect(await screen.findByText(/Dieser Link ist ungültig oder abgelaufen/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(sepaMandatBestaetigen).not.toHaveBeenCalled()
  })

  it('bietet für Änderungen den passenden Button-Text', async () => {
    vi.mocked(sepaMandatVorschau).mockResolvedValue({ ...VORSCHAU, aktion: 'aendern' })
    rendere()
    expect(await screen.findByRole('button', { name: 'Änderung verbindlich bestätigen' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'SEPA-Lastschriftmandat ändern' })).toBeInTheDocument()
  })
})
