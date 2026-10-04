import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { schreibenApi } from '../../../api/korrespondenz'
import { mitarbeiterApi } from '../../../api/mitarbeiter'
import { objekteApi } from '../../../api/objekte'
import { Badge } from '../../../components/ui/Badge'
import type { Schreiben, SchreibenListeParams } from '../../../types'
import { ANLASS_LABEL, ANLASS_OPTIONEN, KANAL_LABEL } from '../konstanten'
import {
  ANZEIGE_STATUS_BADGE, ANZEIGE_STATUS_LABEL, POSTAUSGANG_ANSICHTEN, anzeigeStatus, datumZeit,
} from './schreibenKonstanten'

const feld = 'border border-gray-300 rounded px-2 py-1.5 text-sm'

/** Postausgang (Spec 7.2): Schreiben zur Prüfung, nicht erzeugbare und fehlgeschlagene Sendungen. */
export function PostausgangPage() {
  const [params] = useSearchParams()
  const serienlauf = params.get('serienlauf') ?? ''
  const [ansicht, setAnsicht] = useState(params.get('status') ?? '')
  const [objekt, setObjekt] = useState('')
  const [anlass, setAnlass] = useState('')
  const [betreuer, setBetreuer] = useState('')

  const { data: objekte } = useQuery({ queryKey: ['objekte-sidebar'], queryFn: objekteApi.list })
  const { data: mitarbeiter } = useQuery({ queryKey: ['mitarbeiter-liste'], queryFn: () => mitarbeiterApi.list() })

  const filter = useMemo<SchreibenListeParams>(() => ({
    ...(ansicht ? { status: ansicht } : {}),
    ...(objekt ? { objekt } : {}),
    ...(anlass ? { anlass } : {}),
    ...(betreuer ? { betreuer } : {}),
    ...(serienlauf ? { serienlauf } : {}),
  }), [ansicht, objekt, anlass, betreuer, serienlauf])

  const { data: schreiben, isLoading, error } = useQuery({
    queryKey: ['korrespondenz-schreiben', 'postausgang', filter],
    queryFn: () => schreibenApi.list(filter),
  })

  const zaehler = useMemo(() => {
    const z: Record<string, number> = {}
    for (const s of schreiben ?? []) z[anzeigeStatus(s)] = (z[anzeigeStatus(s)] ?? 0) + 1
    return z
  }, [schreiben])

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Postausgang</h1>
        <div className="ml-auto flex gap-2">
          <Link to="/korrespondenz/druckstapel" className="text-sm text-primary-600 hover:underline">Zum Druckstapel</Link>
          <Link to="/korrespondenz/serienbrief" className="text-sm text-primary-600 hover:underline">Serienbrief</Link>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3 bg-white border border-gray-200 rounded-lg p-3">
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Ansicht</span>
          <select className={feld} value={ansicht} onChange={e => setAnsicht(e.target.value)}>
            {POSTAUSGANG_ANSICHTEN.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Objekt</span>
          <select className={feld} value={objekt} onChange={e => setObjekt(e.target.value)}>
            <option value="">Alle</option>
            {(objekte ?? []).map(o => <option key={o.id} value={o.id}>{o.objektnummer} {o.bezeichnung}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Anlass</span>
          <select className={feld} value={anlass} onChange={e => setAnlass(e.target.value)}>
            <option value="">Alle</option>
            {ANLASS_OPTIONEN.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Betreuer</span>
          <select className={feld} value={betreuer} onChange={e => setBetreuer(e.target.value)}>
            <option value="">Alle</option>
            {(mitarbeiter ?? []).filter(m => m.aktiv).map(m => (
              <option key={m.id} value={String(m.user_id)}>{m.vollname}</option>
            ))}
          </select>
        </label>
        {serienlauf && <p className="text-xs text-gray-500 pb-2">Gefiltert auf einen Serienlauf.</p>}
      </div>

      {isLoading && <p className="text-gray-400">Lade Postausgang…</p>}
      {error && <p role="alert" className="text-red-600">Postausgang konnte nicht geladen werden.</p>}

      {schreiben && (
        <>
          <p className="text-sm text-gray-600" aria-live="polite">
            {schreiben.length} Schreiben
            {Object.entries(zaehler).map(([status, n]) => (
              <span key={status}> · {n} {ANZEIGE_STATUS_LABEL[status as keyof typeof ANZEIGE_STATUS_LABEL] ?? status}</span>
            ))}
          </p>
          <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-3 py-2">Nummer</th>
                  <th className="px-3 py-2">Empfänger</th>
                  <th className="px-3 py-2">Objekt / Einheit</th>
                  <th className="px-3 py-2">Anlass</th>
                  <th className="px-3 py-2">Betreff</th>
                  <th className="px-3 py-2">Kanal</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Erstellt</th>
                </tr>
              </thead>
              <tbody>
                {schreiben.length === 0 && (
                  <tr><td colSpan={8} className="px-3 py-6 text-center text-gray-400">Keine Schreiben im Postausgang.</td></tr>
                )}
                {schreiben.map(s => <PostausgangZeile key={s.id} s={s} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function PostausgangZeile({ s }: { s: Schreiben }) {
  const status = anzeigeStatus(s)
  return (
    <tr className={`border-t border-gray-100 align-top ${status === 'nicht_erzeugbar' ? 'bg-red-50' : 'hover:bg-gray-50'}`}>
      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
        <Link to={`/korrespondenz/postausgang/${s.id}`} className="text-primary-600 hover:underline">{s.nummer}</Link>
      </td>
      <td className="px-3 py-2">{s.empfaenger?.name ?? '–'}</td>
      <td className="px-3 py-2">
        {s.objekt?.bezeichnung ?? '–'}{s.einheit ? ` · Einheit ${s.einheit.einheit_nr}` : ''}
      </td>
      <td className="px-3 py-2">{ANLASS_LABEL[s.vorlage.anlass] ?? s.vorlage.anlass}</td>
      <td className="px-3 py-2">
        {s.betreff || <span className="text-gray-400">–</span>}
        {(status === 'nicht_erzeugbar' || status === 'versand_fehlgeschlagen') && s.fehler && (
          <p className="mt-1 text-xs text-red-700" data-testid="ursache">Ursache: {s.fehler}</p>
        )}
      </td>
      <td className="px-3 py-2 whitespace-nowrap">
        {KANAL_LABEL[s.kanal as keyof typeof KANAL_LABEL] ?? s.kanal}{s.auch_brief && s.kanal !== 'brief' ? ' + Brief' : ''}
      </td>
      <td className="px-3 py-2 whitespace-nowrap">
        <Badge value={ANZEIGE_STATUS_BADGE[status]} label={ANZEIGE_STATUS_LABEL[status]} />
      </td>
      <td className="px-3 py-2 whitespace-nowrap text-gray-600">{datumZeit(s.erstellt_am)}</td>
    </tr>
  )
}
