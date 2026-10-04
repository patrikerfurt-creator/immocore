import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { vorlagenApi } from '../../api/korrespondenz'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { VorlageCreatePayload, VorlagenAnlass, VorlagenKanal } from '../../types'
import { ANLASS_LABEL, ANLASS_OPTIONEN, KANAL_LABEL, fehlerMeldung } from './konstanten'

// Geltungsbereich-Filter: alle | global (objekt = null) | <objekt-id>
const GLOBAL = 'global'

export function KorrVorlagenListe() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [bereich, setBereich] = useState('')
  const [formOffen, setFormOffen] = useState(false)
  const [neu, setNeu] = useState<{
    code: string; bezeichnung: string; anlass: VorlagenAnlass; objekt: string; kanal_standard: VorlagenKanal
  }>({ code: '', bezeichnung: '', anlass: 'eigentuemer_allgemein', objekt: '', kanal_standard: 'brief' })
  const [fehler, setFehler] = useState<string | null>(null)

  const { data: vorlagen, isLoading, error } = useQuery({
    queryKey: ['korrespondenz-vorlagen'],
    queryFn: () => vorlagenApi.list(),
  })
  const { data: objekte } = useQuery({ queryKey: ['objekte-sidebar'], queryFn: objekteApi.list })

  const objektName = useMemo(
    () => new Map((objekte ?? []).map(o => [o.id, `${o.objektnummer} ${o.bezeichnung}`])),
    [objekte],
  )

  const sichtbar = useMemo(() => (vorlagen ?? []).filter(v => {
    if (!bereich) return true
    if (bereich === GLOBAL) return v.objekt == null
    return v.objekt === bereich
  }), [vorlagen, bereich])

  const anlegen = useMutation({
    mutationFn: () => {
      const payload: VorlageCreatePayload = {
        code: neu.code.trim(),
        bezeichnung: neu.bezeichnung.trim(),
        anlass: neu.anlass,
        objekt: neu.objekt || null,
        kanal_standard: neu.kanal_standard,
      }
      return vorlagenApi.create(payload)
    },
    onSuccess: vorlage => {
      qc.invalidateQueries({ queryKey: ['korrespondenz-vorlagen'] })
      navigate(`/korrespondenz/vorlagen/${vorlage.id}`)
    },
    onError: e => setFehler(fehlerMeldung(e, 'Vorlage konnte nicht angelegt werden.')),
  })

  const gueltig = neu.code.trim() !== '' && neu.bezeichnung.trim() !== ''

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Vorlagen &amp; Korrespondenz</h1>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-sm text-gray-600" htmlFor="vorlagen-bereich">Geltungsbereich</label>
          <select id="vorlagen-bereich" value={bereich} onChange={e => setBereich(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm">
            <option value="">Alle</option>
            <option value={GLOBAL}>Nur global</option>
            {(objekte ?? []).map(o => (
              <option key={o.id} value={o.id}>Objekt: {o.objektnummer} {o.bezeichnung}</option>
            ))}
          </select>
          <Button type="button" onClick={() => { setFormOffen(o => !o); setFehler(null) }}>
            {formOffen ? 'Abbrechen' : 'Neue Vorlage'}
          </Button>
        </div>
      </div>

      {formOffen && (
        <form
          className="bg-white border border-gray-200 rounded-lg p-4 grid gap-3 md:grid-cols-5 items-end"
          onSubmit={e => { e.preventDefault(); setFehler(null); if (gueltig) anlegen.mutate() }}
        >
          <label className="text-sm">
            <span className="text-gray-700">Code</span>
            <input value={neu.code} onChange={e => setNeu(n => ({ ...n, code: e.target.value }))}
              placeholder="z. B. eigentuemer_begruessung" maxLength={50}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5 font-mono" />
          </label>
          <label className="text-sm">
            <span className="text-gray-700">Bezeichnung</span>
            <input value={neu.bezeichnung} onChange={e => setNeu(n => ({ ...n, bezeichnung: e.target.value }))}
              maxLength={150} className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <span className="text-gray-700">Anlass</span>
            <select value={neu.anlass} onChange={e => setNeu(n => ({ ...n, anlass: e.target.value as VorlagenAnlass }))}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
              {ANLASS_OPTIONEN.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-gray-700">Objekt (leer = global)</span>
            <select value={neu.objekt} onChange={e => setNeu(n => ({ ...n, objekt: e.target.value }))}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
              <option value="">— global —</option>
              {(objekte ?? []).map(o => <option key={o.id} value={o.id}>{o.objektnummer} {o.bezeichnung}</option>)}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <label className="text-sm flex-1">
              <span className="text-gray-700">Kanal</span>
              <select value={neu.kanal_standard}
                onChange={e => setNeu(n => ({ ...n, kanal_standard: e.target.value as VorlagenKanal }))}
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
                {(Object.keys(KANAL_LABEL) as VorlagenKanal[]).map(k => <option key={k} value={k}>{KANAL_LABEL[k]}</option>)}
              </select>
            </label>
            <Button type="submit" disabled={!gueltig || anlegen.isPending}>Anlegen</Button>
          </div>
          {fehler && <p role="alert" className="md:col-span-5 text-sm text-red-600">{fehler}</p>}
        </form>
      )}

      {isLoading && <p className="text-gray-400">Lade Vorlagen…</p>}
      {error && <p className="text-red-600">Vorlagen konnten nicht geladen werden.</p>}

      {vorlagen && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-3 py-2">Bezeichnung</th>
                <th className="px-3 py-2">Code</th>
                <th className="px-3 py-2">Anlass</th>
                <th className="px-3 py-2">Geltung</th>
                <th className="px-3 py-2">Kanal</th>
                <th className="px-3 py-2">Aktive Version</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {sichtbar.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-6 text-center text-gray-400">Keine Vorlagen.</td></tr>
              )}
              {sichtbar.map(v => (
                <tr key={v.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <Link to={`/korrespondenz/vorlagen/${v.id}`} className="text-primary-600 hover:underline">
                      {v.bezeichnung}
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{v.code}</td>
                  <td className="px-3 py-2">{ANLASS_LABEL[v.anlass] ?? v.anlass}</td>
                  <td className="px-3 py-2">
                    {v.objekt ? (v.objekt_bezeichnung ?? objektName.get(v.objekt) ?? 'Objekt') : 'Global'}
                  </td>
                  <td className="px-3 py-2">{KANAL_LABEL[v.kanal_standard] ?? v.kanal_standard}</td>
                  <td className="px-3 py-2">
                    {v.aktive_version_info ? `Version ${v.aktive_version_info.version}` : v.aktive_version ? 'ja' : '–'}
                  </td>
                  <td className="px-3 py-2">
                    <Badge value={v.aktiv ? 'aktiv' : 'archiviert'} label={v.aktiv ? 'Aktiv' : 'Inaktiv'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
