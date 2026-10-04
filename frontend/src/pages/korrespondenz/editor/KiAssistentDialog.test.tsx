import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { KiAssistentDialog } from './KiAssistentDialog'
import type { KiDialogModus } from './KiAssistentDialog'
import { vorlagenAssistentApi } from '../../../api/korrespondenz'

vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return { ...echt, vorlagenAssistentApi: { entwerfen: vi.fn(), verfuegbar: vi.fn() } }
})

const entwerfen = vi.mocked(vorlagenAssistentApi.entwerfen)

function rendere(modus: KiDialogModus) {
  const onUebernehmen = vi.fn()
  const onSchliessen = vi.fn()
  const onNichtVerfuegbar = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      <KiAssistentDialog modus={modus} anlass="eigentuemer_begruessung"
        onUebernehmen={onUebernehmen} onSchliessen={onSchliessen} onNichtVerfuegbar={onNichtVerfuegbar} />
    </QueryClientProvider>,
  )
  return { onUebernehmen, onSchliessen, onNichtVerfuegbar }
}

function axiosFehler(status: number, data: unknown = {}, code?: string) {
  const e = new AxiosError('x', code)
  e.response = { status, data, statusText: '', headers: {}, config: {} as never }
  return e
}

beforeEach(() => vi.clearAllMocks())

describe('KiAssistentDialog — Mit KI entwerfen', () => {
  it('sendet Anlass + Stichworte, zeigt Blöcke und Hinweise, übernimmt erst auf Klick', async () => {
    entwerfen.mockResolvedValue({
      bloecke: [
        { typ: 'text', inhalt: '<p>Willkommen {{ empfaenger.briefanrede }}</p>' },
        { typ: 'bedingt', bedingung: 'ev.sepa_mandat_fehlt', inhalt: '<p>Bitte SEPA-Mandat senden.</p>' },
      ],
      hinweise: ['Unbekannter Platzhalter: foo.bar'],
    })
    const { onUebernehmen } = rendere({ art: 'entwerfen', bestehendeBloecke: 0 })

    expect(screen.getByRole('button', { name: 'Entwurf erzeugen' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Stichworte'), 'freundliche Begrüßung, SEPA-Hinweis')
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))

    expect(entwerfen).toHaveBeenCalledWith({
      anlass: 'eigentuemer_begruessung', stichworte: 'freundliche Begrüßung, SEPA-Hinweis',
    })
    expect(await screen.findByText('Unbekannter Platzhalter: foo.bar')).toBeInTheDocument()
    expect(screen.getByText(/Willkommen/)).toBeInTheDocument()
    expect(onUebernehmen).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Blöcke anhängen' }))
    expect(onUebernehmen).toHaveBeenCalledWith({
      art: 'anhaengen',
      bloecke: [
        { typ: 'text', inhalt: '<p>Willkommen {{ empfaenger.briefanrede }}</p>' },
        { typ: 'bedingt', bedingung: 'ev.sepa_mandat_fehlt', inhalt: '<p>Bitte SEPA-Mandat senden.</p>' },
      ],
    })
  })

  it('bietet „Alle Blöcke ersetzen“ nur bei vorhandenen Blöcken an', async () => {
    entwerfen.mockResolvedValue({ bloecke: [{ typ: 'text', inhalt: 'x' }], hinweise: [] })
    rendere({ art: 'entwerfen', bestehendeBloecke: 3 })
    await userEvent.type(screen.getByLabelText('Stichworte'), 'kurz')
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))
    expect(await screen.findByRole('button', { name: 'Alle Blöcke ersetzen' })).toBeInTheDocument()
  })

  it('verwirft Blöcke ohne gültige Struktur und weist darauf hin', async () => {
    entwerfen.mockResolvedValue({
      bloecke: [{ typ: 'text', inhalt: 'ok' }, { typ: 'unsinn' } as never],
      hinweise: [],
    })
    rendere({ art: 'entwerfen', bestehendeBloecke: 0 })
    await userEvent.type(screen.getByLabelText('Stichworte'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))
    expect(await screen.findByText(/keine gültige Blockstruktur/)).toBeInTheDocument()
  })

  it('meldet „nicht verfügbar“ (503) an den Editor und schließt sich', async () => {
    entwerfen.mockRejectedValue(axiosFehler(503, { detail: 'KI nicht konfiguriert' }))
    const { onNichtVerfuegbar, onSchliessen } = rendere({ art: 'entwerfen', bestehendeBloecke: 0 })
    await userEvent.type(screen.getByLabelText('Stichworte'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))
    await waitFor(() => expect(onNichtVerfuegbar).toHaveBeenCalled())
    expect(onSchliessen).toHaveBeenCalled()
  })

  it('zeigt Backend-Fehler und Timeout verständlich an', async () => {
    entwerfen.mockRejectedValueOnce(axiosFehler(400, { detail: 'Anlass ungültig' }))
    rendere({ art: 'entwerfen', bestehendeBloecke: 0 })
    await userEvent.type(screen.getByLabelText('Stichworte'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Anlass ungültig')

    entwerfen.mockRejectedValueOnce(axiosFehler(0, null, 'ECONNABORTED'))
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Zeitüberschreitung'))
  })
})

describe('KiAssistentDialog — Mit KI überarbeiten', () => {
  it('sendet den Block mit und ersetzt ihn nach Prüfung', async () => {
    const block = { typ: 'text' as const, inhalt: '<p>Bitte zahlen Sie sofort.</p>' }
    entwerfen.mockResolvedValue({ bloecke: [{ typ: 'text', inhalt: '<p>Wir bitten um Ausgleich.</p>' }], hinweise: [] })
    const { onUebernehmen } = rendere({ art: 'ueberarbeiten', block })

    await userEvent.click(screen.getByRole('button', { name: 'förmlicher' }))
    expect(screen.getByLabelText('Anweisung')).toHaveValue('förmlicher')
    await userEvent.click(screen.getByRole('button', { name: 'Überarbeiten' }))

    expect(entwerfen).toHaveBeenCalledWith({ anlass: 'eigentuemer_begruessung', stichworte: 'förmlicher', block })
    await userEvent.click(await screen.findByRole('button', { name: 'Block ersetzen' }))
    expect(onUebernehmen).toHaveBeenCalledWith({
      art: 'block_ersetzen', bloecke: [{ typ: 'text', inhalt: '<p>Wir bitten um Ausgleich.</p>' }],
    })
  })
})
