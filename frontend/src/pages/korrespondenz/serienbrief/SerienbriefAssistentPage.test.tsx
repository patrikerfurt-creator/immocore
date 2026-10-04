import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SerienbriefAssistentPage, serienbriefVorlagen } from './SerienbriefAssistentPage'
import {
  druckstapelApi, schreibenApi, serienlaeufeApi, vorlagenApi,
} from '../../../api/korrespondenz'
import { mitarbeiterApi } from '../../../api/mitarbeiter'
import { objekteApi } from '../../../api/objekte'
import { personenApi } from '../../../api/personen'
import type { Serienlauf, Vorlage, VorlagenVersion } from '../../../types'
import { fuelle } from '../schreiben/testDaten'

vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return {
    ...echt,
    vorlagenApi: { list: vi.fn(), versionen: vi.fn() },
    serienlaeufeApi: { erzeugen: vi.fn(), get: vi.fn(), freigeben: vi.fn() },
    schreibenApi: { pdf: vi.fn() },
    druckstapelApi: { pdf: vi.fn() },
  }
})
vi.mock('../../../api/objekte', () => ({ objekteApi: { list: vi.fn() } }))
vi.mock('../../../api/mitarbeiter', () => ({ mitarbeiterApi: { list: vi.fn() } }))
vi.mock('../../../api/personen', () => ({ personenApi: { eigentumsverhaeltnisse: vi.fn() } }))

const erzeugen = vi.mocked(serienlaeufeApi.erzeugen)
const laufLaden = vi.mocked(serienlaeufeApi.get)
const laufFreigeben = vi.mocked(serienlaeufeApi.freigeben)

function vorlage(teil: Partial<Vorlage> = {}): Vorlage {
  return {
    id: 'v1', code: 'etv_einladung', bezeichnung: 'ETV-Einladung', anlass: 'etv_einladung', objekt: null,
    briefbogen: null, kanal_standard: 'brief', einzeln_bearbeitbar: false, aktive_version: 'ver1', aktiv: true, ...teil,
  }
}

const VERSION: VorlagenVersion = {
  id: 'ver1', vorlage: 'v1', version: 1, betreff: 'Einladung', status: 'freigegeben', inhalt: [], email_begleittext: '',
  eingabefelder: [{ name: 'ort', label: 'Ort', typ: 'text', pflicht: true }, { name: 'tagesordnung', label: 'Tagesordnung', typ: 'liste', pflicht: false }],
  pflicht_platzhalter: [], parameter: {}, freigegeben_am: '2026-09-01T10:00:00Z',
}

const LAUF: Serienlauf = {
  id: 'lauf-0001', status: 'zur_pruefung', status_anzeige: 'In Prüfung', vorlage_version: 'ver1',
  vorlage: { id: 'v1', code: 'etv_einladung', bezeichnung: 'ETV-Einladung', anlass: 'etv_einladung' },
  objekt: { id: 'o1', bezeichnung: 'Musterstraße 1' }, empfaenger_filter: {}, eingabewerte: {}, unterzeichner: 1, anzahl: 5,
  zaehler: { gesamt: 5, nicht_erzeugbar: 1, je_status: { zur_pruefung: 4, entwurf: 1 } },
  vorschau: {
    erzeugbar_anzahl: 4,
    zufaellig: [
      { schreiben_id: 's1', nummer: 'KS-2026-000001', empfaenger: 'Max Muster', einheit_nr: '12', betreff: 'Einladung ETV', html_gerendert: '<p>x</p>' },
      { schreiben_id: 's2', nummer: 'KS-2026-000002', empfaenger: 'Erika Beispiel', einheit_nr: '14', betreff: 'Einladung ETV', html_gerendert: '<p>y</p>' },
      { schreiben_id: 's3', nummer: 'KS-2026-000003', empfaenger: 'Paul Post', einheit_nr: '3', betreff: 'Einladung ETV', html_gerendert: '<p>z</p>' },
    ],
  },
  nicht_erzeugbar: [
    { schreiben_id: 's9', nummer: 'KS-2026-000009', empfaenger: 'Otto Ohnefläche', einheit_nr: '7', ursache: 'Pflichtwert "einheit.flaeche" fehlt.' },
  ],
  freigebbar: true, blocker: [], druck_dokument: null, druckstapel_ids: [], erstellt_am: '2026-09-29T08:00:00Z', freigegeben_am: null,
}

function rendere() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter><SerienbriefAssistentPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Führt Schritt 1–3 aus und erzeugt die Vorschau. */
async function bisVorschau() {
  await userEvent.click(await screen.findByRole('radio', { name: /ETV-Einladung/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  await userEvent.selectOptions(screen.getByLabelText(/^Objekt [*]/), 'o1')
  await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
  await fuelle(await screen.findByLabelText(/Ort/), 'Saal 1')
  await fuelle(screen.getByLabelText(/Tagesordnung/), 'TOP 1\nTOP 2')
  await userEvent.click(screen.getByRole('button', { name: 'Vorschau erzeugen' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(vorlagenApi.list).mockResolvedValue([
    vorlage(),
    vorlage({ id: 'v-m', code: 'mahnung_stufe_1', bezeichnung: 'Zahlungserinnerung', anlass: 'mahnung_stufe_1' }),
  ])
  vi.mocked(vorlagenApi.versionen).mockResolvedValue([VERSION])
  vi.mocked(objekteApi.list).mockResolvedValue([
    { id: 'o1', objektnummer: '1001', bezeichnung: 'Musterstraße 1' } as never,
    { id: 'o2', objektnummer: '1002', bezeichnung: 'Nebenweg 2' } as never,
  ])
  vi.mocked(mitarbeiterApi.list).mockResolvedValue([{ id: 'm1', user_id: 7, vollname: 'Anna Betreuerin', aktiv: true } as never])
  vi.mocked(personenApi.eigentumsverhaeltnisse).mockResolvedValue([
    { id: 'ev1', person: 'p1', person_name: 'Max Muster', einheit: 'e1', einheit_nr: '12', beginn: '2020-01-01', ende: null, hausgeld_soll: null, ist_aktiv: true, hausgeld_eintraege: [] },
    { id: 'ev2', person: 'p2', person_name: 'Alt Eigentümer', einheit: 'e2', einheit_nr: '14', beginn: '2010-01-01', ende: '2019-12-31', hausgeld_soll: null, ist_aktiv: false, hausgeld_eintraege: [] },
  ])
  vi.mocked(schreibenApi.pdf).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  vi.mocked(druckstapelApi.pdf).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  URL.createObjectURL = vi.fn(() => 'blob:serienbrief-1')
  URL.revokeObjectURL = vi.fn()
})

describe('serienbriefVorlagen', () => {
  it('lässt nur aktive Vorlagen mit freigegebener Version zu, ohne Mahnungen und Vorgangsantworten', () => {
    const ergebnis = serienbriefVorlagen([
      vorlage(),
      vorlage({ id: 'a', aktiv: false }),
      vorlage({ id: 'b', aktive_version: null }),
      vorlage({ id: 'c', anlass: 'mahnung_stufe_2' }),
      vorlage({ id: 'd', anlass: 'vorgang_antwort' }),
    ])
    expect(ergebnis.map(v => v.id)).toEqual(['v1'])
  })
})

describe('SerienbriefAssistentPage', () => {
  it('bietet nur Serienbrief-taugliche Vorlagen an und verlangt eine Auswahl', async () => {
    rendere()
    expect(await screen.findByRole('radio', { name: /ETV-Einladung/ })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /Zahlungserinnerung/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Weiter' })).toBeDisabled()
  })

  it('führt durch alle Schritte, sendet Filter, Angaben und Unterzeichner und zeigt Vorschau samt Fehlerliste', async () => {
    erzeugen.mockResolvedValue(LAUF)
    laufLaden.mockResolvedValue(LAUF)
    rendere()

    await userEvent.click(await screen.findByRole('radio', { name: /ETV-Einladung/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))

    // Schritt 2: Empfängerkreis
    await userEvent.selectOptions(screen.getByLabelText(/^Objekt [*]/), 'o1')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Wohnung' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Nur mit Zustimmung' }))
    await userEvent.selectOptions(await screen.findByLabelText('Ausnahme Max Muster Einheit 12'), 'aus')
    await userEvent.selectOptions(screen.getByLabelText('Ausnahme Alt Eigentümer Einheit 14'), 'zu')
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))

    // Schritt 3: Angaben — „Vorschau erzeugen“ erst mit Pflichtfeld
    expect(screen.getByRole('button', { name: 'Vorschau erzeugen' })).toBeDisabled()
    await fuelle(screen.getByLabelText(/Ort/), 'Saal 1')
    await fuelle(screen.getByLabelText(/Tagesordnung/), 'TOP 1\nTOP 2')
    await userEvent.selectOptions(screen.getByLabelText('Unterzeichner'), '7')
    await userEvent.click(screen.getByRole('button', { name: 'Vorschau erzeugen' }))

    await waitFor(() => expect(erzeugen).toHaveBeenCalledWith({
      vorlage_version: 'ver1',
      objekt: 'o1',
      empfaenger_filter: {
        einheit_typ: ['Wohnung'], email_zustimmung: 'mit', ausschliessen: ['ev1'], hinzufuegen: ['ev2'],
      },
      eingabewerte: { ort: 'Saal 1', tagesordnung: ['TOP 1', 'TOP 2'] },
      unterzeichner: 7,
    }))

    // Schritt 4: Vorschau + nicht erzeugbare Schreiben mit Ursache
    expect(await screen.findByText('Vorschau mit 3 zufälligen Empfängern')).toBeInTheDocument()
    expect(screen.getByText('Erika Beispiel')).toBeInTheDocument()
    const tabelle = screen.getByRole('region', { name: 'Nicht erzeugbare Schreiben' })
    expect(within(tabelle).getByText('Otto Ohnefläche')).toBeInTheDocument()
    expect(within(tabelle).getByText('Pflichtwert "einheit.flaeche" fehlt.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'PDF-Vorschau Max Muster' }))
    await waitFor(() => expect(screen.getByTitle('Vorschau Max Muster')).toHaveAttribute('src', 'blob:serienbrief-1'))
    expect(schreibenApi.pdf).toHaveBeenCalledWith('s1')

    // Nach dem Erzeugen sind Schritt 1–3 gesperrt
    expect(screen.queryByRole('button', { name: 'Zurück' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Neu beginnen' })).toBeInTheDocument()
  })

  it('Freigabe: startet die Verarbeitung und zeigt nach dem Hintergrundlauf das Ergebnis (Polling)', async () => {
    erzeugen.mockResolvedValue(LAUF)
    // Der Hintergrund-Task läuft erst nach der Freigabe: vorher meldet das Backend „zur_pruefung“.
    let freigegeben = false
    laufLaden.mockImplementation(async () => (freigegeben
      ? {
        ...LAUF, status: 'versendet', druckstapel_ids: ['st1'], druck_dokument: 'sammel1',
        zaehler: { gesamt: 5, nicht_erzeugbar: 1, je_status: { versendet: 3, freigegeben: 1, entwurf: 1 } },
      }
      : LAUF))
    laufFreigeben.mockImplementation(async () => {
      freigegeben = true
      return { ...LAUF, status: 'freigegeben' }
    })
    rendere()
    await bisVorschau()
    await userEvent.click(await screen.findByRole('button', { name: 'Weiter zur Freigabe' }))

    expect(screen.getByText(/4 von 5 Schreiben sind erzeugbar, 1 werden übersprungen/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Serienbrief freigeben (4)' }))
    expect(laufFreigeben).toHaveBeenCalledWith('lauf-0001')

    expect(await screen.findByText('Serienbrief verarbeitet.', {}, { timeout: 6000 })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Druckstapel' })).toHaveAttribute('href', '/korrespondenz/druckstapel')
    await waitFor(() => expect(screen.getByTitle('Sammel-PDF')).toHaveAttribute('src', 'blob:serienbrief-1'))
    expect(druckstapelApi.pdf).toHaveBeenCalledWith('sammel1')
  }, 15000)

  it('sperrt die Freigabe und nennt die Blocker, wenn das Backend nicht freigebbar meldet', async () => {
    const blockiert = { ...LAUF, freigebbar: false, blocker: ['Pflichtfeld "Ort" fehlt.'] }
    erzeugen.mockResolvedValue(blockiert)
    laufLaden.mockResolvedValue(blockiert)
    rendere()
    await bisVorschau()
    await userEvent.click(await screen.findByRole('button', { name: 'Weiter zur Freigabe' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Pflichtfeld "Ort" fehlt.')
    expect(screen.getByRole('button', { name: /Serienbrief freigeben/ })).toBeDisabled()
  })

  it('zeigt Fehler beim Erzeugen und bleibt in Schritt 3', async () => {
    erzeugen.mockRejectedValue(Object.assign(new Error('x'), {
      isAxiosError: true, response: { status: 400, data: { detail: 'Der Empfängerkreis ist leer.' } },
    }))
    rendere()
    await bisVorschau()
    expect(await screen.findByRole('alert')).toHaveTextContent('Der Empfängerkreis ist leer.')
    expect(screen.getByRole('button', { name: 'Vorschau erzeugen' })).toBeInTheDocument()
  })

  it('bei objektbezogener Vorlage ist das Objekt fest vorgegeben', async () => {
    vi.mocked(vorlagenApi.list).mockResolvedValue([
      vorlage({ objekt: 'o2', objekt_bezeichnung: 'Nebenweg 2' }),
    ])
    rendere()
    await userEvent.click(await screen.findByRole('radio', { name: /ETV-Einladung/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))
    const objekt = screen.getByLabelText(/^Objekt [*]/)
    expect(objekt).toBeDisabled()
    expect(objekt).toHaveValue('o2')
  })
})
