import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SchreibenErstellenButton, waehlbareVorlagen } from './SchreibenErstellenDialog'
import { schreibenApi, vorlagenApi } from '../../../api/korrespondenz'
import { personenApi } from '../../../api/personen'
import type { Vorlage, VorlagenVersion } from '../../../types'
import { detailMuster, fuelle } from './testDaten'


vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return {
    ...echt,
    schreibenApi: { create: vi.fn() },
    vorlagenApi: { list: vi.fn(), versionen: vi.fn() },
  }
})
vi.mock('../../../api/personen', () => ({
  personenApi: { list: vi.fn(), eigentumsverhaeltnisse: vi.fn() },
}))

const erstellen = vi.mocked(schreibenApi.create)

function vorlage(teil: Partial<Vorlage>): Vorlage {
  return {
    id: 'v1', code: 'x', bezeichnung: 'X', anlass: 'eigentuemer_allgemein', objekt: null, briefbogen: null,
    kanal_standard: 'brief', einzeln_bearbeitbar: false, aktive_version: 'ver1', aktiv: true, ...teil,
  }
}

const ANTWORT = vorlage({
  id: 'v-antwort', code: 'vorgang_antwort', bezeichnung: 'Antwort auf Anfrage', anlass: 'vorgang_antwort',
  einzeln_bearbeitbar: true, aktive_version: 'ver-a',
})
const ALLGEMEIN = vorlage({ id: 'v-allg', code: 'eigentuemer_allgemein', bezeichnung: 'Eigentümerschreiben', aktive_version: 'ver-b' })
const MAHNUNG = vorlage({ id: 'v-m', code: 'mahnung_stufe_1', bezeichnung: 'Zahlungserinnerung', anlass: 'mahnung_stufe_1', aktive_version: 'ver-m' })

function version(id: string, vorlageId: string, felder: VorlagenVersion['eingabefelder'] = []): VorlagenVersion {
  return {
    id, vorlage: vorlageId, version: 1, betreff: 'B', status: 'freigegeben', inhalt: [], email_begleittext: '',
    eingabefelder: felder, pflicht_platzhalter: [], parameter: {}, freigegeben_am: '2026-09-01T10:00:00Z',
  }
}

function rendere(props: Parameters<typeof SchreibenErstellenButton>[0]) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter><SchreibenErstellenButton {...props} /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(vorlagenApi.list).mockResolvedValue([ANTWORT, ALLGEMEIN, MAHNUNG])
  vi.mocked(vorlagenApi.versionen).mockImplementation(async id => {
    if (id === 'v-antwort') return [version('ver-a', 'v-antwort', [{ name: 'antworttext', label: 'Antworttext', typ: 'mehrzeilig', pflicht: true }])]
    if (id === 'v-allg') return [version('ver-b', 'v-allg', [{ name: 'ort', label: 'Ort', typ: 'text', pflicht: false }])]
    return []
  })
  vi.mocked(personenApi.list).mockResolvedValue([])
  vi.mocked(personenApi.eigentumsverhaeltnisse).mockResolvedValue([
    { id: 'ev1', person: 'p1', person_name: 'Max Muster', einheit: 'e1', einheit_nr: '12', beginn: '2020-01-01',
      ende: null, hausgeld_soll: null, ist_aktiv: true, hausgeld_eintraege: [] },
  ])
})

describe('waehlbareVorlagen', () => {
  it('blendet Mahnungen und Vorgangsantworten aus, außer der Anlass ist fest vorgegeben', () => {
    const alle = [ANTWORT, ALLGEMEIN, MAHNUNG]
    expect(waehlbareVorlagen(alle, null, null).map(v => v.id)).toEqual(['v-allg'])
    expect(waehlbareVorlagen(alle, null, 'vorgang_antwort').map(v => v.id)).toEqual(['v-antwort'])
  })

  it('lässt Vorlagen anderer Objekte und ohne freigegebene Version weg; objektbezogen schlägt global', () => {
    const global = vorlage({ id: 'g', code: 'c' })
    const eigenes = vorlage({ id: 'o', code: 'c', objekt: 'o1' })
    const fremdes = vorlage({ id: 'f', code: 'd', objekt: 'o2' })
    const ohneVersion = vorlage({ id: 'n', code: 'e', aktive_version: null })
    expect(waehlbareVorlagen([global, eigenes, fremdes, ohneVersion], 'o1', null).map(v => v.id)).toEqual(['o'])
  })
})

describe('SchreibenErstellenDialog — Vorgangsansicht', () => {
  it('nutzt den festen Anlass vorgang_antwort, füllt Eingabefelder und legt das Schreiben mit Vorgangsbezug an', async () => {
    erstellen.mockResolvedValue(detailMuster({ id: 'neu1', nummer: 'KS-2026-000009' }))
    const onErstellt = vi.fn()
    rendere({
      anlass: 'vorgang_antwort', vorgangId: 'vg1', person: { id: 'p1', name: 'Max Muster' },
      einheitId: 'e1', objektId: 'o1', onErstellt,
    })
    await userEvent.click(screen.getByRole('button', { name: 'Schreiben erstellen' }))

    expect(await screen.findByText('Vorgangsantwort')).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Eigentümerschreiben' })).not.toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Vorlage'), 'v-antwort')

    const senden = screen.getAllByRole('button', { name: 'Schreiben erstellen' }).pop()!
    expect(senden).toBeDisabled() // Pflichtfeld „Antworttext“ fehlt
    await fuelle(await screen.findByLabelText(/Antworttext/), 'Wir kümmern uns darum.')
    expect(senden).toBeEnabled()
    expect(screen.getByText(/im Postausgang angepasst werden/)).toBeInTheDocument()
    await userEvent.click(senden)

    await waitFor(() => expect(erstellen).toHaveBeenCalledWith({
      vorlage_code: 'vorgang_antwort', empfaenger: 'p1', objekt: 'o1', einheit: 'e1', vorgang: 'vg1',
      eingabewerte: { antworttext: 'Wir kümmern uns darum.' },
    }))
    expect(await screen.findByRole('status')).toHaveTextContent('KS-2026-000009 liegt zur Prüfung im Postausgang')
    expect(screen.getByRole('link', { name: 'Im Postausgang öffnen' })).toHaveAttribute('href', '/korrespondenz/postausgang/neu1')
    expect(onErstellt).toHaveBeenCalled()
  })

  it('ohne Person im Vorgang: Empfänger über die Personensuche wählen', async () => {
    vi.mocked(personenApi.list).mockResolvedValue([
      { id: 'p9', personennummer: 'P-9', name: 'Suche Treffer', person_typ: '100', ist_firma: false, email: '', telefon: '' } as never,
    ])
    rendere({ anlass: 'vorgang_antwort', vorgangId: 'vg1', person: null })
    await userEvent.click(screen.getByRole('button', { name: 'Schreiben erstellen' }))
    await fuelle(await screen.findByLabelText('Empfänger suchen'), 'Suche')
    await userEvent.click(await screen.findByRole('button', { name: /Suche Treffer/ }))
    expect(await screen.findByText('Suche Treffer')).toBeInTheDocument()
  })
})

describe('SchreibenErstellenDialog — Personenansicht', () => {
  it('wählt Anlass, Vorlage, Einheit und Kanal; sendet nur gesetzte Felder', async () => {
    vi.mocked(vorlagenApi.list).mockResolvedValue([ALLGEMEIN, vorlage({
      id: 'v-beg', code: 'eigentuemer_begruessung', bezeichnung: 'Begrüßung', anlass: 'eigentuemer_begruessung', aktive_version: 'ver-x',
    })])
    erstellen.mockResolvedValue(detailMuster())
    rendere({ person: { id: 'p1', name: 'Max Muster' } })
    await userEvent.click(screen.getByRole('button', { name: 'Schreiben erstellen' }))

    await userEvent.selectOptions(await screen.findByLabelText('Anlass'), 'eigentuemer_allgemein')
    await userEvent.selectOptions(screen.getByLabelText('Vorlage'), 'v-allg')
    await userEvent.selectOptions(await screen.findByLabelText(/Einheit \(optional\)/), 'ev1')
    await userEvent.selectOptions(screen.getByLabelText('Kanal'), 'email')
    await fuelle(await screen.findByLabelText('Ort'), 'Saal 1')
    await userEvent.click(screen.getAllByRole('button', { name: 'Schreiben erstellen' }).pop()!)

    await waitFor(() => expect(erstellen).toHaveBeenCalledWith({
      vorlage_code: 'eigentuemer_allgemein', empfaenger: 'p1', einheit: 'e1', eigentumsverhaeltnis: 'ev1',
      eingabewerte: { ort: 'Saal 1' }, kanal: 'email',
    }))
  })
})

describe('SchreibenErstellenDialog — Fehlerfälle', () => {
  it('zeigt bei „nicht erzeugbar“ die Ursache und verweist auf den Postausgang', async () => {
    erstellen.mockResolvedValue(detailMuster({
      status: 'entwurf', nicht_erzeugbar: true, fehler: 'Pflichtwert "einheit.flaeche" fehlt.',
    }))
    rendere({ person: { id: 'p1', name: 'Max Muster' }, einheitId: 'e1' })
    await userEvent.click(screen.getByRole('button', { name: 'Schreiben erstellen' }))
    await userEvent.selectOptions(await screen.findByLabelText('Vorlage'), 'v-allg')
    await userEvent.click(screen.getAllByRole('button', { name: 'Schreiben erstellen' }).pop()!)

    const hinweis = await screen.findByRole('alert')
    expect(hinweis).toHaveTextContent('ist nicht erzeugbar')
    expect(hinweis).toHaveTextContent('Pflichtwert "einheit.flaeche" fehlt.')
  })

  it('zeigt den Backend-Fehler, wenn die Vorlage nicht aufgelöst werden kann', async () => {
    erstellen.mockRejectedValue(Object.assign(new Error('x'), {
      isAxiosError: true, response: { status: 400, data: { detail: 'Keine aktive Vorlage gefunden.' } },
    }))
    rendere({ person: { id: 'p1', name: 'Max Muster' }, einheitId: 'e1' })
    await userEvent.click(screen.getByRole('button', { name: 'Schreiben erstellen' }))
    await userEvent.selectOptions(await screen.findByLabelText('Vorlage'), 'v-allg')
    await userEvent.click(screen.getAllByRole('button', { name: 'Schreiben erstellen' }).pop()!)
    expect(await screen.findByRole('alert')).toHaveTextContent('Keine aktive Vorlage gefunden.')
  })
})
