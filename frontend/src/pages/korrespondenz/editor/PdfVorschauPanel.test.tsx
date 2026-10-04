import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { PdfVorschauPanel, eingabewerteAufbereiten } from './PdfVorschauPanel'
import { vorlagenVersionenApi } from '../../../api/korrespondenz'
import { personenApi } from '../../../api/personen'
import type { Eingabefeld, PersonList } from '../../../types'

vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return { ...echt, vorlagenVersionenApi: { update: vi.fn(), freigeben: vi.fn(), vorschau: vi.fn() } }
})
vi.mock('../../../api/personen', () => ({
  personenApi: { list: vi.fn(), eigentumsverhaeltnisse: vi.fn() },
}))

const vorschau = vi.mocked(vorlagenVersionenApi.vorschau)
const personenListe = vi.mocked(personenApi.list)
const evListe = vi.mocked(personenApi.eigentumsverhaeltnisse)

const MUSTER: PersonList = {
  id: 'p1', personennummer: 'P-1001', name: 'Max Muster', person_typ: 'eigentuemer',
  ist_firma: false, email: '', telefon: '',
} as PersonList

const FELDER: Eingabefeld[] = [
  { name: 'ort', label: 'Ort', typ: 'text', pflicht: true },
  { name: 'tagesordnung', label: 'Tagesordnung', typ: 'liste', pflicht: true },
]

function rendere(vorabSpeichern = vi.fn().mockResolvedValue(undefined), felder = FELDER) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <PdfVorschauPanel versionId="ver1" eingabefelder={felder} vorabSpeichern={vorabSpeichern} />
    </QueryClientProvider>,
  )
  return { vorabSpeichern }
}

beforeEach(() => {
  vi.clearAllMocks()
  personenListe.mockResolvedValue([MUSTER])
  evListe.mockResolvedValue([
    { id: 'ev1', person: 'p1', person_name: 'Max Muster', einheit: 'e1', einheit_nr: '12', beginn: '2020-01-01',
      ende: null, hausgeld_soll: null, ist_aktiv: true, hausgeld_eintraege: [] },
  ])
  URL.createObjectURL = vi.fn(() => 'blob:vorschau-1')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => vi.restoreAllMocks())

describe('eingabewerteAufbereiten', () => {
  it('macht aus Listen Arrays, lässt leere Werte weg, übernimmt ja_nein als Boolean', () => {
    const felder: Eingabefeld[] = [
      ...FELDER,
      { name: 'leer', label: '', typ: 'text', pflicht: false },
      { name: 'sepa', label: '', typ: 'ja_nein', pflicht: false },
    ]
    expect(eingabewerteAufbereiten(felder, {
      ort: ' Saal 1 ', tagesordnung: 'TOP 1\n\n TOP 2 ', leer: '  ', sepa: true,
    })).toEqual({ ort: ' Saal 1 ', tagesordnung: ['TOP 1', 'TOP 2'], sepa: true })
  })
})

describe('PdfVorschauPanel', () => {
  it('sucht einen Beispiel-Eigentümer, speichert vorab und zeigt das PDF im iframe (blob-URL)', async () => {
    vorschau.mockResolvedValue(new Blob(['%PDF-1.7'], { type: 'application/pdf' }))
    const { vorabSpeichern } = rendere()

    expect(screen.getByRole('button', { name: 'Vorschau erzeugen' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Beispiel-Eigentümer suchen'), 'Muster')
    await userEvent.click(await screen.findByRole('button', { name: /Max Muster/ }))
    await userEvent.selectOptions(await screen.findByLabelText(/Einheit \(optional\)/), 'e1')

    const eingabeOrt = screen.getByLabelText(/Ort/)
    await userEvent.type(eingabeOrt, 'Saal 1')
    await userEvent.type(screen.getByLabelText(/Tagesordnung/), 'TOP 1{Enter}TOP 2')
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau erzeugen' }))

    await waitFor(() => expect(screen.getByTitle('PDF-Vorschau')).toHaveAttribute('src', 'blob:vorschau-1'))
    expect(vorabSpeichern).toHaveBeenCalledTimes(1)
    expect(vorschau).toHaveBeenCalledWith('ver1', {
      person_id: 'p1', einheit_id: 'e1',
      eingabewerte: { ort: 'Saal 1', tagesordnung: ['TOP 1', 'TOP 2'] },
    })
  })

  it('zeigt die Backend-Fehlermeldung aus dem Blob an und kein iframe', async () => {
    const fehler = new AxiosError('400')
    fehler.response = {
      status: 400, statusText: '', headers: {}, config: {} as never,
      data: new Blob([JSON.stringify({ detail: 'Pflichtwert "ort" fehlt.' })], { type: 'application/json' }),
    }
    vorschau.mockRejectedValue(fehler)
    rendere()
    await userEvent.type(screen.getByLabelText('Beispiel-Eigentümer suchen'), 'Muster')
    await userEvent.click(await screen.findByRole('button', { name: /Max Muster/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau erzeugen' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Pflichtwert "ort" fehlt.')
    expect(screen.queryByTitle('PDF-Vorschau')).not.toBeInTheDocument()
  })

  it('bricht ab, wenn das Vorab-Speichern scheitert (keine Vorschau vom veralteten Stand)', async () => {
    const vorab = vi.fn().mockRejectedValue(new Error('Speichern fehlgeschlagen'))
    rendere(vorab)
    await userEvent.type(screen.getByLabelText('Beispiel-Eigentümer suchen'), 'Muster')
    await userEvent.click(await screen.findByRole('button', { name: /Max Muster/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau erzeugen' }))
    await waitFor(() => expect(vorab).toHaveBeenCalled())
    expect(vorschau).not.toHaveBeenCalled()
  })
})
