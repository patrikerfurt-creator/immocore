import { describe, it, expect, vi, beforeEach } from 'vitest'
import client from './client'
import { druckstapelApi, schreibenApi, serienlaeufeApi } from './korrespondenz'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

const get = vi.mocked(client.get)
const post = vi.mocked(client.post)
const patch = vi.mocked(client.patch)

beforeEach(() => {
  vi.clearAllMocks()
  get.mockResolvedValue({ data: 'GET' })
  post.mockResolvedValue({ data: 'POST' })
  patch.mockResolvedValue({ data: 'PATCH' })
})

describe('schreibenApi — URLs gemäß Spec Abschnitt 8', () => {
  it('Liste mit Filtern, Detail, Anlegen', async () => {
    await schreibenApi.list({ status: 'nicht_erzeugbar', objekt: 'o1', anlass: 'etv_einladung' })
    expect(get).toHaveBeenCalledWith('/korrespondenz/schreiben/', {
      params: { status: 'nicht_erzeugbar', objekt: 'o1', anlass: 'etv_einladung' },
    })
    await schreibenApi.get('s1')
    expect(get).toHaveBeenCalledWith('/korrespondenz/schreiben/s1/')
    await schreibenApi.create({ vorlage_code: 'x', empfaenger: 'p1' })
    expect(post).toHaveBeenCalledWith('/korrespondenz/schreiben/', { vorlage_code: 'x', empfaenger: 'p1' })
  })

  it('Textanpassung: PATCH mit inhalt_angepasst', async () => {
    const inhalt = [{ typ: 'text' as const, inhalt: '<p>Neu</p>' }]
    await schreibenApi.anpassen('s1', inhalt)
    expect(patch).toHaveBeenCalledWith('/korrespondenz/schreiben/s1/', { inhalt_angepasst: inhalt })
  })

  it('Freigeben, Versenden (optional als Brief) und Verwerfen', async () => {
    await schreibenApi.freigeben('s1')
    expect(post).toHaveBeenCalledWith('/korrespondenz/schreiben/s1/freigeben/')
    await schreibenApi.versenden('s1')
    expect(post).toHaveBeenCalledWith('/korrespondenz/schreiben/s1/versenden/', {})
    await schreibenApi.versenden('s1', 'brief')
    expect(post).toHaveBeenCalledWith('/korrespondenz/schreiben/s1/versenden/', { kanal: 'brief' })
    await schreibenApi.verwerfen('s1')
    expect(post).toHaveBeenCalledWith('/korrespondenz/schreiben/s1/verwerfen/')
  })

  it('PDF: Blob-Antwort, kein Accept-Header (sonst 406)', async () => {
    get.mockResolvedValueOnce({ data: new Blob(['%PDF'], { type: 'application/pdf' }) })
    const blob = await schreibenApi.pdf('s1')
    expect(get).toHaveBeenCalledWith('/korrespondenz/schreiben/s1/pdf/', { responseType: 'blob' })
    expect(get.mock.calls[0][1]).not.toHaveProperty('headers')
    expect(blob.type).toBe('application/pdf')
  })
})

describe('druckstapelApi und serienlaeufeApi', () => {
  it('Druckstapel: erzeugen, bestätigen, Sammel-PDF über das DMS als Blob', async () => {
    await druckstapelApi.erzeugen({ objekt: 'o1' })
    expect(post).toHaveBeenCalledWith('/korrespondenz/druckstapel/', { objekt: 'o1' })
    await druckstapelApi.erzeugen()
    expect(post).toHaveBeenCalledWith('/korrespondenz/druckstapel/', {})
    await druckstapelApi.bestaetigen('d1')
    expect(post).toHaveBeenCalledWith('/korrespondenz/druckstapel/d1/bestaetigen/')
    await druckstapelApi.pdf('dok1')
    expect(get).toHaveBeenCalledWith('/dokumente/dok1/datei/', { responseType: 'blob' })
  })

  it('Serienlauf: anlegen, laden, freigeben', async () => {
    await serienlaeufeApi.erzeugen({ objekt: 'o1', vorlage_version: 'ver1' })
    expect(post).toHaveBeenCalledWith('/korrespondenz/serienlaeufe/', { objekt: 'o1', vorlage_version: 'ver1' })
    await serienlaeufeApi.get('l1')
    expect(get).toHaveBeenCalledWith('/korrespondenz/serienlaeufe/l1/')
    await serienlaeufeApi.freigeben('l1')
    expect(post).toHaveBeenCalledWith('/korrespondenz/serienlaeufe/l1/freigeben/')
  })
})
