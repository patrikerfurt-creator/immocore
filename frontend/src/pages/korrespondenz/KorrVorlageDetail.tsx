import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { briefboegenApi, vorlagenApi, vorlagenVersionenApi } from '../../api/korrespondenz'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { Vorlage, VorlagenKanal, VorlagenVersion } from '../../types'
import { ANLASS_LABEL, KANAL_LABEL, VERSION_STATUS_LABEL, fehlerMeldung } from './konstanten'

function datum(s: string | null | undefined) {
  return s ? new Date(s).toLocaleString('de-DE') : '–'
}

/** Vorlagenverwaltung im Detail: Stammdaten der Vorlage, Versionen, Status, Freigeben. */
export function KorrVorlageDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const [meldung, setMeldung] = useState<{ art: 'ok' | 'fehler'; text: string } | null>(null)
  const [form, setForm] = useState<Pick<Vorlage,
    'bezeichnung' | 'kanal_standard' | 'einzeln_bearbeitbar' | 'aktiv' | 'briefbogen'> | null>(null)

  const { data: vorlage, isLoading, error } = useQuery({
    queryKey: ['korrespondenz-vorlage', id],
    queryFn: () => vorlagenApi.get(id!),
    enabled: !!id,
  })
  const { data: versionen } = useQuery({
    queryKey: ['korrespondenz-versionen', id],
    queryFn: () => vorlagenApi.versionen(id!),
    enabled: !!id,
  })
  const { data: objekte } = useQuery({ queryKey: ['objekte-sidebar'], queryFn: objekteApi.list })
  // Briefbögen sind IsAdminUser — für normale Mitarbeiter 403, dann entfällt die Auswahl.
  const { data: briefboegen } = useQuery({
    queryKey: ['korrespondenz-briefboegen'],
    queryFn: briefboegenApi.list,
    retry: false,
  })

  useEffect(() => {
    if (vorlage) {
      setForm({
        bezeichnung: vorlage.bezeichnung,
        kanal_standard: vorlage.kanal_standard,
        einzeln_bearbeitbar: vorlage.einzeln_bearbeitbar,
        aktiv: vorlage.aktiv,
        briefbogen: vorlage.briefbogen,
      })
    }
  }, [vorlage])

  const invalidieren = () => {
    qc.invalidateQueries({ queryKey: ['korrespondenz-vorlage', id] })
    qc.invalidateQueries({ queryKey: ['korrespondenz-versionen', id] })
    qc.invalidateQueries({ queryKey: ['korrespondenz-vorlagen'] })
  }

  const speichern = useMutation({
    mutationFn: () => vorlagenApi.update(id!, form!),
    onSuccess: () => {
      invalidieren()
      setMeldung({ art: 'ok', text: 'Vorlage gespeichert.' })
    },
    onError: e => setMeldung({ art: 'fehler', text: fehlerMeldung(e, 'Speichern fehlgeschlagen.') }),
  })

  // Neue Version = Kopie der jüngsten Version (basis_version); freigegebene Versionen bleiben unverändert.
  const neueVersion = useMutation({
    mutationFn: () => {
      const juengste = [...(versionen ?? [])].sort((a, b) => b.version - a.version)[0]
      return vorlagenApi.versionAnlegen(id!, juengste ? { basis_version: juengste.id } : {})
    },
    onSuccess: () => {
      invalidieren()
      setMeldung({ art: 'ok', text: 'Neue Version als Entwurf angelegt.' })
    },
    onError: e => setMeldung({ art: 'fehler', text: fehlerMeldung(e, 'Version konnte nicht angelegt werden.') }),
  })

  const freigeben = useMutation({
    mutationFn: (v: VorlagenVersion) => vorlagenVersionenApi.freigeben(v.id),
    onSuccess: () => {
      invalidieren()
      setMeldung({ art: 'ok', text: 'Version freigegeben.' })
    },
    onError: e => setMeldung({ art: 'fehler', text: fehlerMeldung(e, 'Freigabe fehlgeschlagen.') }),
  })

  function freigabe(v: VorlagenVersion) {
    if (window.confirm(
      `Version ${v.version} freigeben? Nach der Freigabe ist sie unveränderlich und wird zur aktiven Version.`,
    )) freigeben.mutate(v)
  }

  if (isLoading) return <p className="p-6 text-gray-400">Lade Vorlage…</p>
  if (error || !vorlage || !form) return <p className="p-6 text-red-600">Vorlage konnte nicht geladen werden.</p>

  const objektText = vorlage.objekt
    ? (vorlage.objekt_bezeichnung ?? objekte?.find(o => o.id === vorlage.objekt)?.bezeichnung ?? 'Objekt')
    : 'Global'
  const geordnet = [...(versionen ?? [])].sort((a, b) => b.version - a.version)
  const geaendert =
    form.bezeichnung !== vorlage.bezeichnung || form.kanal_standard !== vorlage.kanal_standard ||
    form.einzeln_bearbeitbar !== vorlage.einzeln_bearbeitbar || form.aktiv !== vorlage.aktiv ||
    form.briefbogen !== vorlage.briefbogen

  return (
    <div className="p-6 space-y-5">
      <div>
        <Link to="/korrespondenz/vorlagen" className="text-sm text-primary-600 hover:underline">← Alle Vorlagen</Link>
        <h1 className="text-xl font-semibold mt-1">{vorlage.bezeichnung}</h1>
        <p className="text-sm text-gray-500">
          {ANLASS_LABEL[vorlage.anlass] ?? vorlage.anlass} · <span className="font-mono">{vorlage.code}</span> · {objektText}
        </p>
      </div>

      {meldung && (
        <p role={meldung.art === 'fehler' ? 'alert' : 'status'}
          className={`text-sm ${meldung.art === 'fehler' ? 'text-red-600' : 'text-green-700'}`}>
          {meldung.text}
        </p>
      )}

      {/* Stammdaten */}
      <section className="bg-white border border-gray-200 rounded-lg p-4 grid gap-3 md:grid-cols-4 items-end" aria-label="Stammdaten">
        <label className="text-sm md:col-span-2">
          <span className="text-gray-700">Bezeichnung</span>
          <input value={form.bezeichnung} onChange={e => setForm({ ...form, bezeichnung: e.target.value })}
            className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5" />
        </label>
        <label className="text-sm">
          <span className="text-gray-700">Standard-Kanal</span>
          <select value={form.kanal_standard}
            onChange={e => setForm({ ...form, kanal_standard: e.target.value as VorlagenKanal })}
            className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
            {(Object.keys(KANAL_LABEL) as VorlagenKanal[]).map(k => <option key={k} value={k}>{KANAL_LABEL[k]}</option>)}
          </select>
        </label>
        {briefboegen && (
          <label className="text-sm">
            <span className="text-gray-700">Briefbogen</span>
            <select value={form.briefbogen ?? ''}
              onChange={e => setForm({ ...form, briefbogen: e.target.value || null })}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
              <option value="">Standard</option>
              {briefboegen.filter(b => b.aktiv).map(b => <option key={b.id} value={b.id}>{b.bezeichnung}</option>)}
            </select>
          </label>
        )}
        <label className="text-sm flex items-center gap-2">
          <input type="checkbox" checked={form.einzeln_bearbeitbar}
            onChange={e => setForm({ ...form, einzeln_bearbeitbar: e.target.checked })} />
          Einzelschreiben vor Freigabe anpassbar
        </label>
        <label className="text-sm flex items-center gap-2">
          <input type="checkbox" checked={form.aktiv} onChange={e => setForm({ ...form, aktiv: e.target.checked })} />
          Aktiv
        </label>
        <div className="md:col-span-2 md:text-right">
          <Button type="button" disabled={!geaendert || speichern.isPending || form.bezeichnung.trim() === ''}
            onClick={() => speichern.mutate()}>
            Speichern
          </Button>
        </div>
      </section>

      {/* Versionen */}
      <section className="bg-white border border-gray-200 rounded-lg" aria-label="Versionen">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold">Versionen</h2>
          <Button type="button" variant="secondary" disabled={neueVersion.isPending} onClick={() => neueVersion.mutate()}>
            + Neue Version
          </Button>
        </div>
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-600">
            <tr>
              <th className="px-4 py-2">Version</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Betreff</th>
              <th className="px-4 py-2">Erstellt</th>
              <th className="px-4 py-2">Freigegeben</th>
              <th className="px-4 py-2 text-right">Aktion</th>
            </tr>
          </thead>
          <tbody>
            {geordnet.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">
                Noch keine Version. Legen Sie mit „Neue Version“ einen Entwurf an.
              </td></tr>
            )}
            {geordnet.map(v => (
              <tr key={v.id} className="border-t border-gray-100">
                <td className="px-4 py-2">
                  {v.version}
                  {vorlage.aktive_version === v.id && (
                    <span className="ml-2 text-xs text-green-700 font-medium">aktiv</span>
                  )}
                </td>
                <td className="px-4 py-2"><Badge value={v.status} label={VERSION_STATUS_LABEL[v.status]} /></td>
                <td className="px-4 py-2 truncate max-w-xs">{v.betreff || <span className="text-gray-400">(kein Betreff)</span>}</td>
                <td className="px-4 py-2">{datum(v.erstellt_am)}</td>
                <td className="px-4 py-2">{datum(v.freigegeben_am)}</td>
                <td className="px-4 py-2 text-right space-x-2 whitespace-nowrap">
                  <Link to={`/korrespondenz/vorlagen/${vorlage.id}/versionen/${v.id}`}
                    className="text-primary-600 hover:underline">
                    {v.status === 'entwurf' ? 'Bearbeiten' : 'Ansehen'}
                  </Link>
                  {v.status === 'entwurf' && (
                    <Button type="button" size="sm" variant="secondary" disabled={freigeben.isPending}
                      onClick={() => freigabe(v)}>
                      Freigeben
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
