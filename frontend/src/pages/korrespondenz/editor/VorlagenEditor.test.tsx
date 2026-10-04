import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { VorlagenEditor } from './VorlagenEditor'
import {
  platzhalterApi, textbausteineApi, vorlagenAssistentApi, vorlagenVersionenApi,
} from '../../../api/korrespondenz'
import type { Platzhalter, Vorlage, VorlagenVersion } from '../../../types'


vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return {
    ...echt,
    platzhalterApi: { list: vi.fn() },
    textbausteineApi: { list: vi.fn() },
    vorlagenAssistentApi: { entwerfen: vi.fn(), verfuegbar: vi.fn() },
    vorlagenVersionenApi: { update: vi.fn(), freigeben: vi.fn(), vorschau: vi.fn() },
  }
})
vi.mock('../../../api/personen', () => ({
  personenApi: { list: vi.fn().mockResolvedValue([]), eigentumsverhaeltnisse: vi.fn().mockResolvedValue([]) },
}))

const platzhalterListe = vi.mocked(platzhalterApi.list)
const bausteinListe = vi.mocked(textbausteineApi.list)
const assistentVerfuegbar = vi.mocked(vorlagenAssistentApi.verfuegbar)
const assistentEntwerfen = vi.mocked(vorlagenAssistentApi.entwerfen)
const versionUpdate = vi.mocked(vorlagenVersionenApi.update)
const versionFreigeben = vi.mocked(vorlagenVersionenApi.freigeben)

const PLATZHALTER: Platzhalter[] = [
  { name: 'empfaenger.briefanrede', beschreibung: 'Briefanrede', typ: 'text', beispiel: 'Sehr geehrter Herr Muster', gruppe: 'empfaenger' },
  { name: 'ev.sepa_mandat_fehlt', beschreibung: 'SEPA-Mandat fehlt', typ: 'bool', beispiel: true, gruppe: 'ev' },
  { name: 'mahnung.offene_posten', beschreibung: 'Offene Posten', typ: 'tabelle', beispiel: null, gruppe: 'mahnung' },
]

const VORLAGE: Vorlage = {
  id: 'v1', code: 'etv_einladung', bezeichnung: 'ETV-Einladung', anlass: 'etv_einladung', objekt: null,
  briefbogen: null, kanal_standard: 'brief', einzeln_bearbeitbar: false, aktive_version: null, aktiv: true,
}

function version(teil: Partial<VorlagenVersion> = {}): VorlagenVersion {
  return {
    id: 'ver1', vorlage: 'v1', version: 2, betreff: 'Einberufung', status: 'entwurf',
    inhalt: [
      { typ: 'text', inhalt: '<p>Sehr geehrte Damen und Herren,</p>' },
      { typ: 'bedingt', bedingung: 'ev.sepa_mandat_fehlt', inhalt: '<p>Bitte SEPA senden.</p>' },
      { typ: 'tabelle', quelle: 'mahnung.offene_posten' },
      { typ: 'liste', quelle: 'eingabe.tagesordnung' },
      { typ: 'seitenumbruch' },
      { typ: 'anlage_seite', titel: 'Vertretungsvollmacht', inhalt: '<p>Hiermit bevollmächtige ich</p>' },
    ],
    email_begleittext: '', eingabefelder: [{ name: 'tagesordnung', label: 'TOPs', typ: 'liste', pflicht: true }],
    pflicht_platzhalter: [], parameter: {}, freigegeben_am: null,
    ...teil,
  }
}

function rendere(v: VorlagenVersion = version()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <VorlagenEditor vorlage={VORLAGE} version={v} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  platzhalterListe.mockResolvedValue(PLATZHALTER)
  bausteinListe.mockResolvedValue([])
  assistentVerfuegbar.mockResolvedValue(true)
  versionUpdate.mockResolvedValue(version())
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})
afterEach(() => vi.restoreAllMocks())

describe('VorlagenEditor — Blockrahmen und Blockstruktur', () => {
  it('rendert je Blocktyp einen Rahmen mit den Feldern des Contracts', async () => {
    rendere()
    for (const name of [
      'Block 1: Text', 'Block 2: Bedingter Text', 'Block 3: Tabelle (systemerzeugt)',
      'Block 4: Liste (aus Eingabefeld)', 'Block 5: Seitenumbruch', 'Block 6: Anlageseite',
    ]) {
      expect(await screen.findByRole('region', { name })).toBeInTheDocument()
    }
    expect(screen.getByDisplayValue('ev.sepa_mandat_fehlt')).toBeInTheDocument()   // bedingung
    expect(screen.getByDisplayValue('mahnung.offene_posten')).toBeInTheDocument()  // tabelle.quelle
    expect(screen.getByDisplayValue('eingabe.tagesordnung')).toBeInTheDocument()   // liste.quelle
    expect(screen.getByDisplayValue('Vertretungsvollmacht')).toBeInTheDocument()   // anlage_seite.titel
    expect(screen.getByDisplayValue('Einberufung')).toBeInTheDocument()            // Betreff
  })

  it('speichert die unveränderte Blockstruktur ohne lokale Schlüssel (PATCH nur mit Änderung)', async () => {
    rendere()
    const speichern = await screen.findByRole('button', { name: 'Speichern' })
    expect(speichern).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: '+ Seitenumbruch' }))
    await userEvent.click(speichern)

    await waitFor(() => expect(versionUpdate).toHaveBeenCalledTimes(1))
    const [id, payload] = versionUpdate.mock.calls[0]
    expect(id).toBe('ver1')
    expect(payload).toEqual({
      betreff: 'Einberufung',
      inhalt: [...version().inhalt, { typ: 'seitenumbruch' }],
      eingabefelder: version().eingabefelder,
      email_begleittext: '',
    })
    expect(await screen.findByText('Gespeichert.')).toBeInTheDocument()
  })

  it('ändert Bedingung, Quelle und Titel und verschiebt/entfernt Blöcke', async () => {
    rendere()
    const bedingung = await screen.findByDisplayValue('ev.sepa_mandat_fehlt')
    await userEvent.clear(bedingung)
    await userEvent.type(bedingung, 'ev.beginn')
    await userEvent.click(screen.getByRole('button', { name: 'Block 6 nach oben' }))   // Anlage vor Seitenumbruch
    await userEvent.click(screen.getByRole('button', { name: 'Block 1 entfernen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => expect(versionUpdate).toHaveBeenCalled())
    const inhalt = versionUpdate.mock.calls[0][1].inhalt!
    expect(inhalt.map(b => b.typ)).toEqual(['bedingt', 'tabelle', 'liste', 'anlage_seite', 'seitenumbruch'])
    expect(inhalt[0]).toMatchObject({ typ: 'bedingt', bedingung: 'ev.beginn' })
  })

  it('legt Blöcke aller Typen mit leeren Contract-Feldern an', async () => {
    rendere(version({ inhalt: [] }))
    await screen.findByText(/Noch keine Blöcke/)
    for (const label of [
      'Text', 'Textbaustein', 'Tabelle (systemerzeugt)', 'Liste (aus Eingabefeld)',
      'Bedingter Text', 'Seitenumbruch', 'Anlageseite',
    ]) {
      await userEvent.click(screen.getByRole('button', { name: `+ ${label}` }))
    }
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(versionUpdate).toHaveBeenCalled())
    expect(versionUpdate.mock.calls[0][1].inhalt).toEqual([
      { typ: 'text', inhalt: '' }, { typ: 'baustein', code: '' }, { typ: 'tabelle', quelle: '' },
      { typ: 'liste', quelle: '' }, { typ: 'bedingt', bedingung: '', inhalt: '' },
      { typ: 'seitenumbruch' }, { typ: 'anlage_seite', titel: '', inhalt: '' },
    ])
  })
})

describe('VorlagenEditor — Platzhalter', () => {
  it('lädt die Platzhalter je Anlass und ergänzt Eingabefelder als Chips', async () => {
    rendere()
    const leiste = await screen.findByRole('complementary', { name: 'Platzhalter' })
    expect(platzhalterListe).toHaveBeenCalledWith('etv_einladung')
    expect(await within(leiste).findByRole('button', { name: 'briefanrede' })).toBeInTheDocument()
    expect(within(leiste).getByRole('button', { name: 'tagesordnung' })).toBeInTheDocument()
  })

  it('fügt einen Chip per Klick in den Betreff ein', async () => {
    rendere()
    const leiste = await screen.findByRole('complementary', { name: 'Platzhalter' })
    const chip = await within(leiste).findByRole('button', { name: 'briefanrede' })
    const betreff = screen.getByDisplayValue('Einberufung') as HTMLInputElement
    await userEvent.click(betreff)
    betreff.setSelectionRange(betreff.value.length, betreff.value.length)
    await userEvent.click(chip)
    expect(betreff).toHaveValue('Einberufung{{ empfaenger.briefanrede }}')
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeEnabled()
  })

  it('warnt vor unbekannten Platzhaltern', async () => {
    rendere(version({ betreff: 'Hallo {{ erfunden.feld }}' }))
    expect(await screen.findByText(/Unbekannte Platzhalter/)).toHaveTextContent('erfunden.feld')
  })

  it('weist ohne Fokus auf ein Textfeld darauf hin', async () => {
    rendere()
    const leiste = await screen.findByRole('complementary', { name: 'Platzhalter' })
    await userEvent.click(await within(leiste).findByRole('button', { name: 'briefanrede' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('zuerst in ein Textfeld')
  })
})

describe('VorlagenEditor — KI-Assistent', () => {
  it('zeigt „Mit KI entwerfen“ und je Textblock „Mit KI überarbeiten“', async () => {
    rendere()
    expect(await screen.findByRole('button', { name: /Mit KI entwerfen/ })).toBeInTheDocument()
    // Text, bedingt und Anlageseite haben einen Textkörper
    expect(screen.getAllByRole('button', { name: /Mit KI überarbeiten/ })).toHaveLength(3)
  })

  it('blendet die KI-Buttons aus, wenn der Assistent nicht verfügbar ist', async () => {
    assistentVerfuegbar.mockResolvedValue(false)
    rendere()
    await screen.findByRole('region', { name: 'Block 1: Text' })
    await waitFor(() => expect(assistentVerfuegbar).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('button', { name: /Mit KI entwerfen/ })).not.toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Mit KI überarbeiten/ })).not.toBeInTheDocument()
  })

  it('blendet die KI-Buttons aus, sobald ein Aufruf „nicht verfügbar“ (503) meldet', async () => {
    const e = new AxiosError('503')
    e.response = { status: 503, data: {}, statusText: '', headers: {}, config: {} as never }
    assistentEntwerfen.mockRejectedValue(e)
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: /Mit KI entwerfen/ }))
    await userEvent.type(screen.getByLabelText('Stichworte'), 'kurz')
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /Mit KI entwerfen/ })).not.toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('hängt den geprüften KI-Entwurf an und markiert den Stand als ungespeichert', async () => {
    assistentEntwerfen.mockResolvedValue({
      bloecke: [{ typ: 'text', inhalt: '<p>KI-Absatz</p>' }], hinweise: ['Bitte Fristen prüfen'],
      betreff: 'Einladung zur Versammlung',
    })
    rendere(version({ betreff: '', inhalt: [{ typ: 'text', inhalt: '<p>Alt</p>' }] }))
    await userEvent.click(await screen.findByRole('button', { name: /Mit KI entwerfen/ }))
    await userEvent.type(screen.getByLabelText('Stichworte'), 'Begrüßung')
    await userEvent.click(screen.getByRole('button', { name: 'Entwurf erzeugen' }))
    expect(await screen.findByText('Bitte Fristen prüfen')).toBeInTheDocument()
    // Die im Editor definierten Eingabefelder gehen (ohne Werte) an die KI
    expect(assistentEntwerfen).toHaveBeenCalledWith({
      anlass: 'etv_einladung', stichworte: 'Begrüßung', eingabefelder: version().eingabefelder,
    })
    // Betreff-Vorschlag ist bei leerem Betreff vorausgewählt
    expect(screen.getByRole('checkbox', { name: /Betreff übernehmen/ })).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Blöcke anhängen' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Block 2: Text' })).toBeInTheDocument()
    expect(screen.getByText('Ungespeicherte Änderungen')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(versionUpdate).toHaveBeenCalled())
    expect(versionUpdate.mock.calls[0][1].inhalt).toEqual([
      { typ: 'text', inhalt: '<p>Alt</p>' }, { typ: 'text', inhalt: '<p>KI-Absatz</p>' },
    ])
    expect(versionUpdate.mock.calls[0][1].betreff).toBe('Einladung zur Versammlung')
  })

  it('überarbeitet einen Block: sendet ihn mit und ersetzt ihn erst nach Übernahme', async () => {
    assistentEntwerfen.mockResolvedValue({ bloecke: [{ typ: 'text', inhalt: '<p>Neu formuliert</p>' }], hinweise: [] })
    rendere(version({ inhalt: [{ typ: 'text', inhalt: '<p>Alt</p>' }] }))
    await userEvent.click(await screen.findByRole('button', { name: /Mit KI überarbeiten/ }))
    await userEvent.click(screen.getByRole('button', { name: 'kürzer' }))
    await userEvent.click(screen.getByRole('button', { name: 'Überarbeiten' }))
    expect(assistentEntwerfen).toHaveBeenCalledWith({
      anlass: 'etv_einladung', stichworte: 'kürzer', block: { typ: 'text', inhalt: '<p>Alt</p>' },
      eingabefelder: version().eingabefelder,
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Block ersetzen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(versionUpdate).toHaveBeenCalled())
    expect(versionUpdate.mock.calls[0][1].inhalt).toEqual([{ typ: 'text', inhalt: '<p>Neu formuliert</p>' }])
  })
})

describe('VorlagenEditor — Freigabe und Lesemodus', () => {
  it('speichert vor der Freigabe und gibt nach Bestätigung frei', async () => {
    versionFreigeben.mockResolvedValue(version({ status: 'freigegeben' }))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: '+ Seitenumbruch' }))
    await userEvent.click(screen.getByRole('button', { name: 'Freigeben' }))

    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() => expect(versionFreigeben).toHaveBeenCalledWith('ver1'))
    expect(versionUpdate).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('Version freigegeben.')).toBeInTheDocument()
  })

  it('gibt nicht frei, wenn die Bestätigung abgelehnt wird', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben' }))
    expect(versionFreigeben).not.toHaveBeenCalled()
  })

  it('zeigt Freigabe-Fehler (z. B. fehlende Permission) an', async () => {
    const e = new AxiosError('403')
    e.response = { status: 403, data: { detail: 'Keine Berechtigung zur Vorlagenfreigabe.' }, statusText: '', headers: {}, config: {} as never }
    versionFreigeben.mockRejectedValue(e)
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Keine Berechtigung zur Vorlagenfreigabe.')
  })

  it('zeigt eine freigegebene Version schreibgeschützt (keine Bearbeitungs- und KI-Buttons)', async () => {
    rendere(version({ status: 'freigegeben' }))
    await screen.findByRole('region', { name: 'Block 1: Text' })
    expect(screen.getByText(/nicht mehr änderbar/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Speichern' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Freigeben' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Mit KI/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Seitenumbruch' })).not.toBeInTheDocument()
    expect(screen.getByDisplayValue('Einberufung')).toBeDisabled()
    // Vorschau bleibt möglich
    expect(screen.getByRole('button', { name: 'Vorschau erzeugen' })).toBeInTheDocument()
  })
})
