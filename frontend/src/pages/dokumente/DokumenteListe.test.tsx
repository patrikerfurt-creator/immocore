import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DokumenteListe } from './DokumenteListe'
import { dokumenteApi } from '../../api/dokumente'
import { objekteApi } from '../../api/objekte'
import type { Dokument } from '../../types'

// API-Module werden vollständig gemockt — die Komponente wird isoliert von echten
// HTTP-Aufrufen getestet (API-Vertrag Belegübersicht-Anreicherung v1.0).
vi.mock('../../api/dokumente', () => ({
  dokumenteApi: {
    list: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    listByObjekt: vi.fn(),
    openDatei: vi.fn(),
  },
}))

vi.mock('../../api/objekte', () => ({
  objekteApi: {
    list: vi.fn(),
  },
}))

const mockList = vi.mocked(dokumenteApi.list)
const mockObjekteList = vi.mocked(objekteApi.list)

/** Rendert die Komponente mit den für sie nötigen Providern (Router + React-Query). */
function renderKomponente() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DokumenteListe />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

/** Vollständig befüllter Beleg gemäß API-Vertrag v1.0 als Testdaten-Grundlage. */
function baseDokument(overrides: Partial<Dokument> = {}): Dokument {
  return {
    id: '1',
    objekt: 'obj-1',
    dateiname: 'rechnung.pdf',
    kategorie: 'rechnung',
    datei: '/media/rechnung.pdf',
    hochgeladen_am: '2026-01-10T10:00:00Z',
    beschreibung: '',
    rechnungsdatum: '2026-01-05',
    eingangsdatum: '2026-01-06T09:00:00Z',
    kreditor_name: 'Muster GmbH',
    kreditor_unbestaetigt: false,
    betrag_brutto: '1234.56',
    kurztext: 'Wartung Heizungsanlage',
    kurztext_volltext: null,
    loeschbar: true,
    loeschsperre_grund: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockObjekteList.mockResolvedValue([])
})

describe('DokumenteListe – Belegübersicht-Anreicherung', () => {
  it('zeigt das Hinweis-Icon mit korrektem Tooltip bei kreditor_unbestaetigt=true', async () => {
    mockList.mockResolvedValue([baseDokument({ kreditor_unbestaetigt: true })])

    renderKomponente()

    await screen.findByText('Muster GmbH', { exact: false })
    expect(
      screen.getByTitle('Kreditor nicht eindeutig zugeordnet – Name aus Rechnungstext, kein Stammdatensatz')
    ).toBeInTheDocument()
  })

  it('zeigt kein Hinweis-Icon bei kreditor_unbestaetigt=false', async () => {
    mockList.mockResolvedValue([baseDokument({ kreditor_unbestaetigt: false })])

    renderKomponente()

    await screen.findByText('Muster GmbH', { exact: false })
    expect(
      screen.queryByTitle('Kreditor nicht eindeutig zugeordnet – Name aus Rechnungstext, kein Stammdatensatz')
    ).not.toBeInTheDocument()
  })

  it('rendert vollständige Belegdaten korrekt formatiert', async () => {
    mockList.mockResolvedValue([
      baseDokument({
        rechnungsdatum: '2026-12-25',
        betrag_brutto: '1234.56',
        kreditor_name: 'Musterfirma GmbH',
        kurztext: 'Wartung Heizungsanlage',
      }),
    ])

    renderKomponente()

    await screen.findByText('Musterfirma GmbH', { exact: false })
    expect(screen.getByText('25.12.2026')).toBeInTheDocument()
    expect(screen.getByText('1.234,56 €')).toBeInTheDocument()
    expect(screen.getByText('Wartung Heizungsanlage')).toBeInTheDocument()
  })

  it('polstert einstelligen Tag und Monat auf TT.MM.JJJJ (Spec Abschnitt 6)', async () => {
    mockList.mockResolvedValue([
      baseDokument({ rechnungsdatum: '2026-01-05', kreditor_name: 'Padding GmbH' }),
    ])

    renderKomponente()

    await screen.findByText('Padding GmbH', { exact: false })
    expect(screen.getByText('05.01.2026')).toBeInTheDocument()
    expect(screen.queryByText('5.1.2026')).not.toBeInTheDocument()
  })

  it('zeigt bei fehlendem Rechnungsdatum einen Platzhalter, übrige Spalten bleiben gefüllt', async () => {
    mockList.mockResolvedValue([
      baseDokument({
        rechnungsdatum: null,
        betrag_brutto: '500.00',
        kreditor_name: 'Handwerksbetrieb Muster',
      }),
    ])

    renderKomponente()

    const kreditorZelle = await screen.findByText('Handwerksbetrieb Muster', { exact: false })
    const zeile = kreditorZelle.closest('tr') as HTMLElement
    const zellen = within(zeile).getAllByRole('cell')

    // Reihenfolge: 0=Kreditor, 1=Kurztext, 2=Bruttobetrag, 3=Rechnungsdatum, 4=Eingangsdatum
    expect(zellen[3].textContent).toBe('–')
    expect(within(zeile).getByText('500,00 €')).toBeInTheDocument()
    expect(within(zeile).getByText('Handwerksbetrieb Muster', { exact: false })).toBeInTheDocument()
  })

  it('fasst Belegspalten bei fehlendem Rechnungsbezug zu einer Zelle zusammen, keine vier Platzhalter', async () => {
    mockList.mockResolvedValue([
      baseDokument({
        dateiname: 'vertrag.pdf',
        rechnungsdatum: null,
        eingangsdatum: null,
        kreditor_name: null,
        kreditor_unbestaetigt: null,
        betrag_brutto: null,
        kurztext: null,
        kurztext_volltext: null,
      }),
    ])

    renderKomponente()

    const oeffnenButton = await screen.findByTitle('vertrag.pdf')
    const zeile = oeffnenButton.closest('tr') as HTMLElement
    const zellen = within(zeile).getAllByRole('cell')

    // Zusammengefasste Belegzelle (colSpan=5) + Kategorie/Beschreibung/Hochgeladen/Aktionen = 5 <td>
    expect(zellen).toHaveLength(5)
    expect(zellen[0]).toHaveAttribute('colspan', '5')
    // In der Sammelzelle steht der Dateiname — ohne Rechnungsbezug ist er der
    // einzige Identifikator der Zeile. Keine „–"-Platzhalter.
    expect(zellen[0].textContent).toBe('vertrag.pdf')
    expect(zellen[0].textContent).not.toContain('–')
  })

  it('zeigt die Spalten in der geforderten Reihenfolge ohne Dateiname-Spalte', async () => {
    mockList.mockResolvedValue([baseDokument()])
    renderKomponente()
    await screen.findByText('Muster GmbH', { exact: false })

    const kopfzellen = screen.getAllByRole('columnheader').map(th => th.textContent?.trim())
    expect(kopfzellen).toEqual([
      'Kreditor', 'Kurztext', 'Bruttobetrag', 'Rechnungsdatum', 'Eingangsdatum',
      'Kategorie', 'Beschreibung', 'Hochgeladen am', 'Aktionen',
    ])
    expect(kopfzellen).not.toContain('Dateiname')
  })

  it('zeigt den technischen Dateinamen nicht als Text, hält ihn aber am Öffnen-Button erreichbar', async () => {
    mockList.mockResolvedValue([baseDokument({ dateiname: 'scan_4711_ZUGFeRD.pdf' })])
    renderKomponente()
    await screen.findByText('Muster GmbH', { exact: false })

    expect(screen.queryByText('scan_4711_ZUGFeRD.pdf')).not.toBeInTheDocument()
    expect(screen.getByTitle('scan_4711_ZUGFeRD.pdf')).toBeInTheDocument()
  })

  it('öffnet das Dokument über den Öffnen-Button', async () => {
    mockList.mockResolvedValue([baseDokument({ id: 'dok-42' })])
    renderKomponente()
    await screen.findByText('Muster GmbH', { exact: false })

    await userEvent.setup().click(screen.getByRole('button', { name: 'Öffnen' }))
    expect(dokumenteApi.openDatei).toHaveBeenCalledWith('dok-42')
  })

  it('zeigt den Dateinamen nur ohne Rechnungsbezug, nicht bei Belegen', async () => {
    mockList.mockResolvedValue([
      baseDokument({ id: 'beleg-1', dateiname: 'scan_beleg.pdf' }),
      baseDokument({
        id: 'vertrag-1',
        dateiname: 'mietvertrag.pdf',
        rechnungsdatum: null,
        eingangsdatum: null,
        kreditor_name: null,
        kreditor_unbestaetigt: null,
        betrag_brutto: null,
        kurztext: null,
        kurztext_volltext: null,
      }),
    ])

    renderKomponente()

    // Vertrag: Dateiname sichtbar. Beleg: nur als Tooltip am Öffnen-Button.
    expect(await screen.findByText('mietvertrag.pdf')).toBeInTheDocument()
    expect(screen.queryByText('scan_beleg.pdf')).not.toBeInTheDocument()
  })

  it('sortiert nach Bruttobetrag: erster Klick aufsteigend, zweiter Klick absteigend', async () => {
    mockList.mockResolvedValue([baseDokument()])
    renderKomponente()
    await screen.findByText('Muster GmbH', { exact: false })

    const user = userEvent.setup()

    // Kopf-Zelle nach jedem Klick neu ermitteln statt Referenz wiederzuverwenden:
    // Während des Nachladens (isLoading) wird die Tabelle kurzzeitig durch
    // "Laden…" ersetzt, eine gemerkte Node-Referenz wäre dann losgelöst (detached).
    await user.click(screen.getByText('Bruttobetrag', { exact: false }))
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(
        expect.objectContaining({ ordering: 'rechnung__betrag_brutto' })
      )
    })
    await screen.findByText('Muster GmbH', { exact: false })

    await user.click(screen.getByText('Bruttobetrag', { exact: false }))
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(
        expect.objectContaining({ ordering: '-rechnung__betrag_brutto' })
      )
    })
  })

  it('sortiert nach Rechnungsdatum: erster Klick aufsteigend, zweiter Klick absteigend', async () => {
    mockList.mockResolvedValue([baseDokument()])
    renderKomponente()
    await screen.findByText('Muster GmbH', { exact: false })

    const user = userEvent.setup()

    await user.click(screen.getByText('Rechnungsdatum', { exact: false }))
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(
        expect.objectContaining({ ordering: 'rechnung__rechnungsdatum' })
      )
    })
    await screen.findByText('Muster GmbH', { exact: false })

    await user.click(screen.getByText('Rechnungsdatum', { exact: false }))
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(
        expect.objectContaining({ ordering: '-rechnung__rechnungsdatum' })
      )
    })
  })
})

describe('DokumenteListe – Löschsperre (API-Vertrag v1.1)', () => {
  it('deaktiviert den Löschen-Button bei loeschbar=false und zeigt loeschsperre_grund als Tooltip', async () => {
    mockList.mockResolvedValue([
      baseDokument({
        loeschbar: false,
        loeschsperre_grund: 'Rechnung ist geprüft (Status: Zur Freigabe) — Beleg muss erhalten bleiben.',
      }),
    ])

    renderKomponente()

    const loeschenButton = await screen.findByRole('button', { name: 'Löschen' })
    expect(loeschenButton).toBeDisabled()
    expect(loeschenButton).toHaveAttribute(
      'title',
      'Rechnung ist geprüft (Status: Zur Freigabe) — Beleg muss erhalten bleiben.'
    )
  })

  it('lässt den Löschen-Button bei loeschbar=true aktiv', async () => {
    mockList.mockResolvedValue([baseDokument({ loeschbar: true, loeschsperre_grund: null })])

    renderKomponente()

    const loeschenButton = await screen.findByRole('button', { name: 'Löschen' })
    expect(loeschenButton).not.toBeDisabled()
  })

  it('löst bei Klick auf den deaktivierten Löschen-Button keinen Löschaufruf aus', async () => {
    mockList.mockResolvedValue([
      baseDokument({ loeschbar: false, loeschsperre_grund: 'Beleg ist mit einer Rechnung verknüpft — zuerst die Rechnung entfernen.' }),
    ])

    renderKomponente()

    const loeschenButton = await screen.findByRole('button', { name: 'Löschen' })
    await userEvent.setup().click(loeschenButton)

    expect(dokumenteApi.delete).not.toHaveBeenCalled()
  })

  it('lässt den Öffnen-Button bei loeschbar=false aktiv', async () => {
    mockList.mockResolvedValue([baseDokument({ id: 'dok-99', loeschbar: false, loeschsperre_grund: 'Revisionssicherer Beleg (GoBD) — Löschen nicht zulässig.' })])

    renderKomponente()

    const oeffnenButton = await screen.findByRole('button', { name: 'Öffnen' })
    expect(oeffnenButton).not.toBeDisabled()

    await userEvent.setup().click(oeffnenButton)
    expect(dokumenteApi.openDatei).toHaveBeenCalledWith('dok-99')
  })
})
