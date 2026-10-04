import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KorrVorlagenListe } from './KorrVorlagenListe'
import { KorrVorlageDetail } from './KorrVorlageDetail'
import { VorlagenEditorPage } from './VorlagenEditorPage'
import {
  briefboegenApi, platzhalterApi, textbausteineApi, vorlagenApi, vorlagenAssistentApi, vorlagenVersionenApi,
} from '../../api/korrespondenz'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'
import type { Vorlage, VorlagenVersion } from '../../types'


vi.mock('../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../api/korrespondenz')>('../../api/korrespondenz')
  return {
    ...echt,
    vorlagenApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), versionen: vi.fn(), versionAnlegen: vi.fn() },
    vorlagenVersionenApi: { update: vi.fn(), freigeben: vi.fn(), vorschau: vi.fn() },
    briefboegenApi: { list: vi.fn() },
    platzhalterApi: { list: vi.fn() },
    textbausteineApi: { list: vi.fn() },
    vorlagenAssistentApi: { entwerfen: vi.fn(), verfuegbar: vi.fn() },
  }
})
vi.mock('../../api/objekte', () => ({ objekteApi: { list: vi.fn() } }))
vi.mock('../../api/personen', () => ({
  personenApi: { list: vi.fn(), eigentumsverhaeltnisse: vi.fn() },
}))

const liste = vi.mocked(vorlagenApi.list)
const holen = vi.mocked(vorlagenApi.get)
const anlegen = vi.mocked(vorlagenApi.create)
const versionen = vi.mocked(vorlagenApi.versionen)
const versionAnlegen = vi.mocked(vorlagenApi.versionAnlegen)
const freigeben = vi.mocked(vorlagenVersionenApi.freigeben)
const briefboegen = vi.mocked(briefboegenApi.list)
const objekte = vi.mocked(objekteApi.list)

const GLOBAL: Vorlage = {
  id: 'v1', code: 'etv_einladung', bezeichnung: 'ETV-Einladung', anlass: 'etv_einladung', objekt: null,
  briefbogen: null, kanal_standard: 'brief', einzeln_bearbeitbar: false,
  aktive_version: 'ver1', aktive_version_info: { id: 'ver1', version: 1, status: 'freigegeben' }, aktiv: true,
}
const OBJEKTBEZOGEN: Vorlage = {
  ...GLOBAL, id: 'v2', code: 'etv_einladung', bezeichnung: 'ETV-Einladung Musterstraße', objekt: 'o1',
  aktive_version: null, aktive_version_info: null,
}

const VER1: VorlagenVersion = {
  id: 'ver1', vorlage: 'v1', version: 1, betreff: 'Einberufung', status: 'freigegeben',
  inhalt: [{ typ: 'text', inhalt: '<p>Text</p>' }], email_begleittext: '', eingabefelder: [],
  pflicht_platzhalter: [], parameter: { frist_tage: 14 }, freigegeben_am: '2026-09-01T10:00:00Z',
}
const VER2: VorlagenVersion = { ...VER1, id: 'ver2', version: 2, status: 'entwurf', freigegeben_am: null, betreff: 'Entwurf 2' }

function rendere(pfad: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}>
        <Routes>
          <Route path="/korrespondenz/vorlagen" element={<KorrVorlagenListe />} />
          <Route path="/korrespondenz/vorlagen/:id" element={<KorrVorlageDetail />} />
          <Route path="/korrespondenz/vorlagen/:id/versionen/:versionId" element={<VorlagenEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(platzhalterApi.list).mockResolvedValue([])
  vi.mocked(textbausteineApi.list).mockResolvedValue([])
  vi.mocked(vorlagenAssistentApi.verfuegbar).mockResolvedValue(true)
  vi.mocked(personenApi.list).mockResolvedValue([])
  vi.mocked(personenApi.eigentumsverhaeltnisse).mockResolvedValue([])
  objekte.mockResolvedValue([{ id: 'o1', objektnummer: '1001', bezeichnung: 'Musterstraße 1' } as never])
  briefboegen.mockRejectedValue(new Error('403'))
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})
afterEach(() => vi.restoreAllMocks())

describe('Vorlagenliste', () => {
  it('listet Vorlagen mit Geltung, filtert nach global und je Objekt', async () => {
    liste.mockResolvedValue([GLOBAL, OBJEKTBEZOGEN])
    rendere('/korrespondenz/vorlagen')

    expect(await screen.findByRole('link', { name: 'ETV-Einladung' })).toHaveAttribute('href', '/korrespondenz/vorlagen/v1')
    expect(screen.getByRole('link', { name: 'ETV-Einladung Musterstraße' })).toBeInTheDocument()
    expect(screen.getByText('Version 1')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Geltungsbereich'), 'global')
    expect(screen.queryByRole('link', { name: 'ETV-Einladung Musterstraße' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ETV-Einladung' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Geltungsbereich'), 'o1')
    expect(screen.queryByRole('link', { name: 'ETV-Einladung' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ETV-Einladung Musterstraße' })).toBeInTheDocument()
  })

  it('legt eine Vorlage an und springt in deren Detail', async () => {
    liste.mockResolvedValue([])
    anlegen.mockResolvedValue({ ...GLOBAL, id: 'neu' })
    holen.mockResolvedValue({ ...GLOBAL, id: 'neu' })
    versionen.mockResolvedValue([])
    rendere('/korrespondenz/vorlagen')

    await userEvent.click(await screen.findByRole('button', { name: 'Neue Vorlage' }))
    await userEvent.type(screen.getByLabelText('Code'), 'mahnung_stufe_1')
    await userEvent.type(screen.getByLabelText('Bezeichnung'), 'Zahlungserinnerung')
    await userEvent.selectOptions(screen.getByLabelText('Anlass'), 'mahnung_stufe_1')
    await userEvent.click(screen.getByRole('button', { name: 'Anlegen' }))

    await waitFor(() => expect(anlegen).toHaveBeenCalledWith({
      code: 'mahnung_stufe_1', bezeichnung: 'Zahlungserinnerung', anlass: 'mahnung_stufe_1',
      objekt: null, kanal_standard: 'brief',
    }))
    expect(await screen.findByRole('heading', { name: 'ETV-Einladung' })).toBeInTheDocument()
  })
})

describe('Vorlagen-Detail (Versionen)', () => {
  beforeEach(() => {
    holen.mockResolvedValue(GLOBAL)
    versionen.mockResolvedValue([VER1, VER2])
  })

  it('zeigt Versionen mit Status, aktiver Markierung und Aktionen je Status', async () => {
    rendere('/korrespondenz/vorlagen/v1')
    const tabelle = await screen.findByRole('region', { name: 'Versionen' })
    const zeilen = within(tabelle).getAllByRole('row')
    // Kopf + Version 2 (neueste zuerst) + Version 1
    expect(zeilen).toHaveLength(3)
    expect(within(zeilen[1]).getByText('Entwurf')).toBeInTheDocument()
    expect(within(zeilen[1]).getByRole('link', { name: 'Bearbeiten' }))
      .toHaveAttribute('href', '/korrespondenz/vorlagen/v1/versionen/ver2')
    expect(within(zeilen[1]).getByRole('button', { name: 'Freigeben' })).toBeInTheDocument()
    expect(within(zeilen[2]).getByText('Freigegeben')).toBeInTheDocument()
    expect(within(zeilen[2]).getByText('aktiv')).toBeInTheDocument()
    expect(within(zeilen[2]).getByRole('link', { name: 'Ansehen' })).toBeInTheDocument()
    expect(within(zeilen[2]).queryByRole('button', { name: 'Freigeben' })).not.toBeInTheDocument()
  })

  it('gibt einen Entwurf nach Bestätigung frei', async () => {
    freigeben.mockResolvedValue({ ...VER2, status: 'freigegeben' })
    rendere('/korrespondenz/vorlagen/v1')
    const tabelle = await screen.findByRole('region', { name: 'Versionen' })
    await userEvent.click(within(tabelle).getByRole('button', { name: 'Freigeben' }))
    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() => expect(freigeben).toHaveBeenCalledWith('ver2'))
    expect(await screen.findByText('Version freigegeben.')).toBeInTheDocument()
  })

  it('legt eine neue Version als Kopie der jüngsten an (basis_version)', async () => {
    versionAnlegen.mockResolvedValue({ ...VER2, id: 'ver3', version: 3 })
    rendere('/korrespondenz/vorlagen/v1')
    await userEvent.click(await screen.findByRole('button', { name: '+ Neue Version' }))
    await waitFor(() => expect(versionAnlegen).toHaveBeenCalledWith('v1', { basis_version: 'ver2' }))
  })

  it('bietet die Briefbogen-Auswahl nur, wenn die Briefbögen ladbar sind (Admin)', async () => {
    rendere('/korrespondenz/vorlagen/v1')
    await screen.findByRole('region', { name: 'Stammdaten' })
    expect(screen.queryByLabelText('Briefbogen')).not.toBeInTheDocument()
  })

  it('speichert Änderungen der Stammdaten per PATCH', async () => {
    briefboegen.mockResolvedValue([{ id: 'b1', bezeichnung: 'Demme Standard', aktiv: true } as never])
    vi.mocked(vorlagenApi.update).mockResolvedValue(GLOBAL)
    rendere('/korrespondenz/vorlagen/v1')
    await userEvent.selectOptions(await screen.findByLabelText('Briefbogen'), 'b1')
    await userEvent.click(screen.getByLabelText(/Einzelschreiben vor Freigabe anpassbar/))
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(vorlagenApi.update).toHaveBeenCalledWith('v1', {
      bezeichnung: 'ETV-Einladung', kanal_standard: 'brief', einzeln_bearbeitbar: true, aktiv: true, briefbogen: 'b1',
    }))
  })
})

describe('Editor-Seite', () => {
  it('lädt Vorlage + Versionsliste und zeigt die gewählte Version', async () => {
    holen.mockResolvedValue(GLOBAL)
    versionen.mockResolvedValue([VER1, VER2])
    rendere('/korrespondenz/vorlagen/v1/versionen/ver2')
    expect(await screen.findByDisplayValue('Entwurf 2')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /ETV-Einladung/ })).toHaveTextContent('Version 2')
  })

  it('meldet eine unbekannte Version', async () => {
    holen.mockResolvedValue(GLOBAL)
    versionen.mockResolvedValue([VER1])
    rendere('/korrespondenz/vorlagen/v1/versionen/gibt-es-nicht')
    expect(await screen.findByText('Version nicht gefunden.')).toBeInTheDocument()
  })
})
