import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AxiosError } from 'axios'
import client from './client'
import {
  ASSISTENT_TIMEOUT_MS, briefboegenApi, istAssistentNichtVerfuegbar, korrespondenzFehlerText,
  platzhalterApi, textbausteineApi, vorlagenApi, vorlagenAssistentApi, vorlagenVersionenApi,
} from './korrespondenz'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

const get = vi.mocked(client.get)
const post = vi.mocked(client.post)
const patch = vi.mocked(client.patch)
const del = vi.mocked(client.delete)

function axiosFehler(status: number, data: unknown = {}) {
  const e = new AxiosError('fehler')
  e.response = { status, data, statusText: '', headers: {}, config: {} as never }
  return e
}

beforeEach(() => {
  vi.clearAllMocks()
  get.mockResolvedValue({ data: 'GET' })
  post.mockResolvedValue({ data: 'POST' })
  patch.mockResolvedValue({ data: 'PATCH' })
  del.mockResolvedValue({ data: null })
})

describe('korrespondenz API-Client — URLs gemäß Spec Abschnitt 8', () => {
  it('Platzhalter je Anlass', async () => {
    await platzhalterApi.list('mahnung_stufe_1')
    expect(get).toHaveBeenCalledWith('/korrespondenz/platzhalter/', { params: { anlass: 'mahnung_stufe_1' } })
  })

  it('Vorlagen: list/get/create/update', async () => {
    await vorlagenApi.list({ objekt: 'o1' })
    expect(get).toHaveBeenCalledWith('/korrespondenz/vorlagen/', { params: { objekt: 'o1' } })
    await vorlagenApi.get('v1')
    expect(get).toHaveBeenCalledWith('/korrespondenz/vorlagen/v1/')
    await vorlagenApi.create({ code: 'c', bezeichnung: 'B', anlass: 'etv_einladung' })
    expect(post).toHaveBeenCalledWith('/korrespondenz/vorlagen/', { code: 'c', bezeichnung: 'B', anlass: 'etv_einladung' })
    await vorlagenApi.update('v1', { aktiv: false })
    expect(patch).toHaveBeenCalledWith('/korrespondenz/vorlagen/v1/', { aktiv: false })
  })

  it('Versionen: Liste/Anlegen unter der Vorlage, PATCH/Freigeben unter /versionen/', async () => {
    await vorlagenApi.versionen('v1')
    expect(get).toHaveBeenCalledWith('/korrespondenz/vorlagen/v1/versionen/')
    await vorlagenApi.versionAnlegen('v1', { betreff: 'X' })
    expect(post).toHaveBeenCalledWith('/korrespondenz/vorlagen/v1/versionen/', { betreff: 'X' })
    await vorlagenVersionenApi.update('ver1', { betreff: 'Y' })
    expect(patch).toHaveBeenCalledWith('/korrespondenz/versionen/ver1/', { betreff: 'Y' })
    await vorlagenVersionenApi.freigeben('ver1')
    expect(post).toHaveBeenCalledWith('/korrespondenz/versionen/ver1/freigeben/')
  })

  it('Vorschau: POST mit Person/Einheit/Eingabewerte, Antwort als Blob', async () => {
    post.mockResolvedValueOnce({ data: new Blob(['%PDF'], { type: 'application/pdf' }) })
    const blob = await vorlagenVersionenApi.vorschau('ver1', { person_id: 'p1', einheit_id: 'e1', eingabewerte: { a: 1 } })
    expect(post).toHaveBeenCalledWith(
      '/korrespondenz/versionen/ver1/vorschau/',
      { person_id: 'p1', einheit_id: 'e1', eingabewerte: { a: 1 } },
      { responseType: 'blob' },
    )
    expect(blob.type).toBe('application/pdf')
  })

  it('Textbausteine und Briefbögen: CRUD-Pfade', async () => {
    await textbausteineApi.list()
    expect(get).toHaveBeenCalledWith('/korrespondenz/textbausteine/', { params: undefined })
    await textbausteineApi.create({ code: 'x', bezeichnung: 'X', inhalt: 'i' })
    expect(post).toHaveBeenCalledWith('/korrespondenz/textbausteine/', { code: 'x', bezeichnung: 'X', inhalt: 'i' })
    await textbausteineApi.update('t1', { aktiv: false })
    expect(patch).toHaveBeenCalledWith('/korrespondenz/textbausteine/t1/', { aktiv: false })
    await textbausteineApi.delete('t1')
    expect(del).toHaveBeenCalledWith('/korrespondenz/textbausteine/t1/')
    await briefboegenApi.list()
    expect(get).toHaveBeenCalledWith('/korrespondenz/briefboegen/')
    await briefboegenApi.update('b1', { aktiv: false })
    expect(patch).toHaveBeenCalledWith('/korrespondenz/briefboegen/b1/', { aktiv: false })
  })

  it('KI-Assistent: POST mit 65-s-Timeout', async () => {
    await vorlagenAssistentApi.entwerfen({ anlass: 'etv_einladung', stichworte: 'kurz' })
    expect(post).toHaveBeenCalledWith(
      '/korrespondenz/vorlagen-assistent/',
      { anlass: 'etv_einladung', stichworte: 'kurz' },
      { timeout: ASSISTENT_TIMEOUT_MS },
    )
    expect(ASSISTENT_TIMEOUT_MS).toBeGreaterThan(60_000)
  })
})

describe('KI-Assistent: Verfügbarkeit', () => {
  it('501/503 und verfuegbar:false bedeuten „nicht verfügbar“', () => {
    expect(istAssistentNichtVerfuegbar(axiosFehler(503))).toBe(true)
    expect(istAssistentNichtVerfuegbar(axiosFehler(501))).toBe(true)
    expect(istAssistentNichtVerfuegbar(axiosFehler(400, { verfuegbar: false }))).toBe(true)
    expect(istAssistentNichtVerfuegbar(axiosFehler(400, { detail: 'x' }))).toBe(false)
    expect(istAssistentNichtVerfuegbar(new Error('x'))).toBe(false)
  })

  it('verfuegbar(): false bei verfuegbar:false oder 503, sonst true (auch bei 405 = kein GET-Vertrag)', async () => {
    get.mockResolvedValueOnce({ data: { verfuegbar: false } })
    expect(await vorlagenAssistentApi.verfuegbar()).toBe(false)
    get.mockRejectedValueOnce(axiosFehler(503))
    expect(await vorlagenAssistentApi.verfuegbar()).toBe(false)
    get.mockRejectedValueOnce(axiosFehler(405))
    expect(await vorlagenAssistentApi.verfuegbar()).toBe(true)
    get.mockResolvedValueOnce({ data: { verfuegbar: true } })
    expect(await vorlagenAssistentApi.verfuegbar()).toBe(true)
  })
})

describe('korrespondenzFehlerText', () => {
  it('liest detail aus JSON', async () => {
    expect(await korrespondenzFehlerText(axiosFehler(400, { detail: 'Pflichtwert fehlt' }), 'x')).toBe('Pflichtwert fehlt')
  })

  it('liest die JSON-Fehlermeldung aus einem Blob (PDF-Vorschau)', async () => {
    const blob = new Blob([JSON.stringify({ detail: 'Render-Fehler' })], { type: 'application/json' })
    expect(await korrespondenzFehlerText(axiosFehler(400, blob), 'x')).toBe('Render-Fehler')
  })

  it('fällt auf den Fallback zurück', async () => {
    expect(await korrespondenzFehlerText(new Error('x'), 'Fallback')).toBe('Fallback')
    expect(await korrespondenzFehlerText(axiosFehler(500, null), 'Fallback')).toBe('Fallback')
  })
})
