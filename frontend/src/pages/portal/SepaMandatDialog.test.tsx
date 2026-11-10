import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SepaMandatDialog } from './SepaMandatDialog'
import { ibanPruefen, sepaMandatAnfordern } from '../../api/portal'
import type { SepaMandatStatus } from '../../api/portal'

vi.mock('../../api/portal', async () => {
  const echt = await vi.importActual<typeof import('../../api/portal')>('../../api/portal')
  return { ...echt, ibanPruefen: vi.fn(), sepaMandatAnfordern: vi.fn() }
})

const GUELTIGE_IBAN = 'DE89370400440532013000'

const MANDAT = {
  mandatsreferenz: 'M2024-090', iban_maskiert: 'DE89 **** 3000', bic: 'COBADEFFXXX',
  unterzeichnet_am: '2024-03-05', quelle: 'verwaltung' as const,
}

function status(teil: Partial<SepaMandatStatus>): SepaMandatStatus {
  return {
    kann_erteilen: true, hinderungsgrund: null, empfaenger_email_maskiert: 'm***@example.de',
    kopfzeile_aktion: 'erteilen', auswahl_noetig: false, offene_anfrage: null,
    geltungsbereiche: [{ schluessel: 'alle', ev_id: null, bezeichnung: 'Alle Einheiten', aktion: 'erteilen', mandat: null }],
    ...teil,
  }
}

const MIT_AUSWAHL = status({
  kopfzeile_aktion: 'aendern', auswahl_noetig: true,
  geltungsbereiche: [
    { schluessel: 'alle', ev_id: null, bezeichnung: 'Alle Einheiten', aktion: 'aendern', mandat: MANDAT },
    { schluessel: 'ev:u1', ev_id: 'u1', bezeichnung: 'Hauptstr. 1, WE 12', objekt_bezeichnung: 'Hauptstr. 1',
      einheit_nr: '12', lage: '1. OG', aktion: 'erteilen', mandat: null, wirksam_ueber: 'alle' },
  ],
})

function rendere(st: SepaMandatStatus, onClose = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <SepaMandatDialog status={st} onClose={onClose} />
    </QueryClientProvider>,
  )
  return onClose
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(ibanPruefen).mockResolvedValue({ valid: true, iban: GUELTIGE_IBAN, bic: 'COBADEFFXXX', bank_name: 'Commerzbank' })
  vi.mocked(sepaMandatAnfordern).mockResolvedValue({
    detail: 'Wir haben Ihnen einen Bestätigungslink gesendet.', empfaenger_email_maskiert: 'm***@example.de',
    gueltig_bis: '2026-11-05T10:00:00Z',
  })
})

describe('SepaMandatDialog', () => {
  it('zeigt ohne Auswahlzwang keine Radiogruppe und den Titel "erteilen"', () => {
    rendere(status({}))
    expect(screen.getByRole('dialog', { name: 'SEPA-Lastschriftmandat erteilen' })).toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.getByText(/m\*\*\*@example\.de/)).toBeInTheDocument()
  })

  it('wechselt den Titel je nach gewähltem Geltungsbereich', async () => {
    const user = userEvent.setup()
    rendere(MIT_AUSWAHL)
    expect(screen.getAllByRole('radio')).toHaveLength(2)
    expect(screen.getByRole('dialog', { name: 'SEPA-Lastschriftmandat ändern' })).toBeInTheDocument()
    expect(screen.getByText(/Aktuelles Mandat: M2024-090/)).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'Für eine bestimmte Einheit' }))
    expect(screen.getByRole('dialog', { name: 'SEPA-Lastschriftmandat erteilen' })).toBeInTheDocument()
    expect(screen.getByText(/gilt derzeit Ihr Sammelmandat/)).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /Sammelmandat/ }))
    expect(screen.getByRole('dialog', { name: 'SEPA-Lastschriftmandat ändern' })).toBeInTheDocument()
  })

  it('zeigt bei kann_erteilen=false nur den Hinderungsgrund', () => {
    rendere(status({ kann_erteilen: false, hinderungsgrund: 'Keine E-Mail-Adresse hinterlegt.' }))
    expect(screen.getByText('Keine E-Mail-Adresse hinterlegt.')).toBeInTheDocument()
    expect(screen.queryByText('IBAN')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bestätigungslink anfordern' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Schließen' })).toBeInTheDocument()
  })

  it('weist auf eine offene Anfrage hin, ohne das Formular zu sperren', () => {
    rendere(status({ offene_anfrage: { schluessel: 'alle', aktion: 'erteilen', erstellt_am: '2026-11-04T10:00:00Z', gueltig_bis: '2026-11-05T10:00:00Z' } }))
    expect(screen.getByText(/liegt bereits eine Anfrage vor/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Bestätigungslink anfordern' })).toBeInTheDocument()
  })

  it('sendet erst bei gültiger IBAN und übergibt Schlüssel und IBAN', async () => {
    const user = userEvent.setup()
    rendere(MIT_AUSWAHL)
    const senden = screen.getByRole('button', { name: 'Bestätigungslink anfordern' })
    expect(senden).toBeDisabled()

    await user.click(screen.getByRole('radio', { name: 'Für eine bestimmte Einheit' }))
    await user.type(screen.getByPlaceholderText(/DE89/), GUELTIGE_IBAN)
    await waitFor(() => expect(senden).toBeEnabled())
    await user.click(senden)

    await waitFor(() => expect(sepaMandatAnfordern).toHaveBeenCalledTimes(1))
    expect(vi.mocked(sepaMandatAnfordern).mock.calls[0][0]).toEqual({
      schluessel: 'ev:u1', iban: GUELTIGE_IBAN, bic: 'COBADEFFXXX',
    })
    expect(await screen.findByText('Wir haben Ihnen einen Bestätigungslink gesendet.')).toBeInTheDocument()
  })

  it('zeigt den Server-Fehler bei abgelehnter Anfrage', async () => {
    vi.mocked(sepaMandatAnfordern).mockRejectedValue({ response: { status: 429, data: {} } })
    const user = userEvent.setup()
    rendere(status({}))
    await user.type(screen.getByPlaceholderText(/DE89/), GUELTIGE_IBAN)
    const senden = screen.getByRole('button', { name: 'Bestätigungslink anfordern' })
    await waitFor(() => expect(senden).toBeEnabled())
    await user.click(senden)
    expect(await screen.findByText('Zu viele Anfragen. Bitte versuchen Sie es später erneut.')).toBeInTheDocument()
  })

  it('schließt mit Esc', async () => {
    const user = userEvent.setup()
    const onClose = rendere(status({}))
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
