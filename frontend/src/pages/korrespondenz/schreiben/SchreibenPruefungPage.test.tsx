import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { SchreibenPruefungPage } from './SchreibenPruefungPage'
import { platzhalterApi, schreibenApi, vorlagenApi } from '../../../api/korrespondenz'
import type { SchreibenVersandAntwort, VorlagenVersion } from '../../../types'
import { detailMuster, fuelle } from './testDaten'


vi.mock('../../../api/korrespondenz', async () => {
  const echt = await vi.importActual<typeof import('../../../api/korrespondenz')>('../../../api/korrespondenz')
  return {
    ...echt,
    schreibenApi: { get: vi.fn(), pdf: vi.fn(), freigeben: vi.fn(), versenden: vi.fn(), verwerfen: vi.fn(), anpassen: vi.fn() },
    vorlagenApi: { versionen: vi.fn() },
    platzhalterApi: { list: vi.fn() },
  }
})
// TipTap wird in den Editor-Tests geprüft; hier genügt ein Textfeld mit gleicher Schnittstelle.
vi.mock('../editor/BlockTextEditor', () => ({
  BlockTextEditor: ({ label, inhalt, onChange }: { label: string; inhalt: string; onChange: (s: string) => void }) => (
    <textarea aria-label={label} defaultValue={inhalt} onChange={e => onChange(e.target.value)} />
  ),
}))

const holen = vi.mocked(schreibenApi.get)
const pdf = vi.mocked(schreibenApi.pdf)
const freigeben = vi.mocked(schreibenApi.freigeben)
const versenden = vi.mocked(schreibenApi.versenden)
const verwerfen = vi.mocked(schreibenApi.verwerfen)
const anpassen = vi.mocked(schreibenApi.anpassen)

const VERSION: VorlagenVersion = {
  id: 'ver1', vorlage: 'v1', version: 1, betreff: 'Antwort', status: 'freigegeben',
  inhalt: [{ typ: 'text', inhalt: '<p>Guten Tag</p>' }, { typ: 'baustein', code: 'gruss' }],
  email_begleittext: '', eingabefelder: [], pflicht_platzhalter: [], parameter: {}, freigegeben_am: '2026-09-01T10:00:00Z',
}

function versandAntwort(ergebnis: 'versendet' | 'druckstapel' | 'fehlgeschlagen', hinweis = ''): SchreibenVersandAntwort {
  return { ...detailMuster({ status: 'freigegeben' }), versand: { ergebnis, hinweis } }
}

function rendere() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter initialEntries={['/korrespondenz/postausgang/s1']}>
        <Routes>
          <Route path="/korrespondenz/postausgang" element={<p>Postausgang-Liste</p>} />
          <Route path="/korrespondenz/postausgang/:id" element={<SchreibenPruefungPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  holen.mockResolvedValue(detailMuster())
  pdf.mockResolvedValue(new Blob(['%PDF-1.7'], { type: 'application/pdf' }))
  vi.mocked(vorlagenApi.versionen).mockResolvedValue([VERSION])
  vi.mocked(platzhalterApi.list).mockResolvedValue([])
  URL.createObjectURL = vi.fn(() => 'blob:schreiben-1')
  URL.revokeObjectURL = vi.fn()
})

describe('SchreibenPruefungPage', () => {
  it('lädt die fertige PDF-Vorschau als Blob in den iframe', async () => {
    rendere()
    await waitFor(() => expect(screen.getByTitle('Schreiben-Vorschau')).toHaveAttribute('src', 'blob:schreiben-1'))
    expect(pdf).toHaveBeenCalledWith('s1')
    expect(screen.getByRole('button', { name: 'Freigeben' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Freigeben & Senden' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Verwerfen' })).toBeEnabled()
  })

  it('bietet die Textanpassung nur an, wenn die Vorlage einzeln_bearbeitbar ist', async () => {
    rendere()
    await screen.findByText('Einladung ETV')
    expect(screen.queryByRole('button', { name: /Text anpassen/ })).not.toBeInTheDocument()
  })

  it('Freigeben & Senden: erst freigeben, dann versenden; zeigt das Ergebnis', async () => {
    freigeben.mockResolvedValue(detailMuster({ status: 'freigegeben', dokument: 'dok1' }))
    versenden.mockResolvedValue(versandAntwort('versendet'))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben & Senden' }))

    expect(await screen.findByText('Freigegeben und versendet.')).toBeInTheDocument()
    expect(freigeben).toHaveBeenCalledWith('s1')
    expect(versenden).toHaveBeenCalledWith('s1')
    expect(freigeben.mock.invocationCallOrder[0]).toBeLessThan(versenden.mock.invocationCallOrder[0])
  })

  it('Freigeben ohne Senden ruft den Versand nicht auf', async () => {
    freigeben.mockResolvedValue(detailMuster({ status: 'freigegeben', dokument: 'dok1' }))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben' }))
    expect(await screen.findByText(/Freigegeben\. Das PDF ist im DMS abgelegt/)).toBeInTheDocument()
    expect(versenden).not.toHaveBeenCalled()
  })

  it('meldet einen fehlgeschlagenen Versand nach erfolgreicher Freigabe', async () => {
    freigeben.mockResolvedValue(detailMuster({ status: 'freigegeben', dokument: 'dok1' }))
    versenden.mockResolvedValue(versandAntwort('fehlgeschlagen', 'Kein SMTP konfiguriert.'))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben & Senden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Freigegeben, aber der Versand ist fehlgeschlagen: Kein SMTP konfiguriert.')
  })

  it('zeigt die Backend-Meldung, wenn die Freigabe scheitert', async () => {
    const e = new AxiosError('400')
    e.response = { status: 400, statusText: '', headers: {}, config: {} as never, data: { detail: 'Freigabe nicht möglich, Schreiben nicht erzeugbar: Pflichtwert fehlt' } }
    freigeben.mockRejectedValue(e)
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Freigeben & Senden' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Pflichtwert fehlt')
    expect(versenden).not.toHaveBeenCalled()
  })

  it('Verwerfen verlangt eine Bestätigung und kehrt zum Postausgang zurück', async () => {
    verwerfen.mockResolvedValue(detailMuster({ status: 'verworfen' }))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: 'Verwerfen' }))
    expect(verwerfen).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Ja, verwerfen' }))
    expect(await screen.findByText('Postausgang-Liste')).toBeInTheDocument()
    expect(verwerfen).toHaveBeenCalledWith('s1')
  })

  it('„nicht erzeugbar“: zeigt die Ursache, lädt kein PDF und erlaubt nur Verwerfen', async () => {
    holen.mockResolvedValue(detailMuster({
      status: 'entwurf', nicht_erzeugbar: true, fehler: 'Pflichtwert "einheit.flaeche" fehlt.',
    }))
    rendere()
    expect(await screen.findByRole('alert')).toHaveTextContent('Pflichtwert "einheit.flaeche" fehlt.')
    expect(pdf).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Freigeben' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Verwerfen' })).toBeInTheDocument()
  })

  it('bei fehlgeschlagenem Versand: erneut senden oder als Brief senden', async () => {
    holen.mockResolvedValue(detailMuster({ status: 'versand_fehlgeschlagen', fehler: 'Kein SMTP konfiguriert.', dokument: 'dok1', kanal: 'email' }))
    versenden.mockResolvedValue(versandAntwort('druckstapel'))
    rendere()
    expect(await screen.findByRole('button', { name: 'Erneut senden' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Als Brief senden' }))
    expect(versenden).toHaveBeenCalledWith('s1', 'brief')
    expect(await screen.findByText(/wartet im Druckstapel/)).toBeInTheDocument()
  })
})

describe('SchreibenPruefungPage — Textanpassung (einzeln_bearbeitbar)', () => {
  beforeEach(() => {
    holen.mockResolvedValue(detailMuster({
      einzeln_bearbeitbar: true, vorlage: { id: 'v1', code: 'vorgang_antwort', bezeichnung: 'Vorgangsantwort', anlass: 'vorgang_antwort' },
    }))
  })

  it('speichert den geänderten Text als inhalt_angepasst (komplette Blockliste) und lädt die Vorschau neu', async () => {
    const angepasst = detailMuster({ einzeln_bearbeitbar: true, inhalt_angepasst: [] })
    anpassen.mockResolvedValue(angepasst)
    rendere()
    await waitFor(() => expect(pdf).toHaveBeenCalledTimes(1))

    await userEvent.click(await screen.findByRole('button', { name: /Text anpassen/ }))
    const feld = await screen.findByLabelText('Text Block 1')
    expect(screen.getByRole('button', { name: 'Text speichern' })).toBeDisabled()
    expect(screen.getByText('Baustein „gruss“')).toBeInTheDocument()

    await fuelle(feld, ' Herr Muster')
    await userEvent.click(screen.getByRole('button', { name: 'Text speichern' }))

    await waitFor(() => expect(anpassen).toHaveBeenCalledWith('s1', [
      { typ: 'text', inhalt: '<p>Guten Tag</p> Herr Muster' },
      { typ: 'baustein', code: 'gruss' },
    ]))
    await waitFor(() => expect(pdf).toHaveBeenCalledTimes(2))
  })

  it('startet mit dem bereits angepassten Text, falls vorhanden', async () => {
    holen.mockResolvedValue(detailMuster({
      einzeln_bearbeitbar: true, inhalt_angepasst: [{ typ: 'text', inhalt: '<p>Angepasst</p>' }],
    }))
    rendere()
    await userEvent.click(await screen.findByRole('button', { name: /Text anpassen/ }))
    expect(await screen.findByLabelText('Text Block 1')).toHaveValue('<p>Angepasst</p>')
  })
})
