import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { druckstapelApi, korrespondenzFehlerText, schreibenApi } from '../../../api/korrespondenz'
import { objekteApi } from '../../../api/objekte'
import { Button } from '../../../components/ui/Button'
import type { Druckstapel, Schreiben } from '../../../types'
import { PdfAnzeige } from './PdfAnzeige'
import { datumZeit } from './schreibenKonstanten'

const MERKER_KEY = 'korrespondenz-druckstapel-dokumente'

/**
 * Das Backend liefert keinen Lese-Endpunkt für Druckstapel; die Dokument-Id des Sammel-PDFs
 * kommt nur in der Antwort von `POST /druckstapel/`. Damit der Stapel nach einem Neuladen der
 * Seite noch angezeigt werden kann, merkt sich der Browser sie (Stapel-Id → Dokument-Id).
 */
export function ladeMerker(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(MERKER_KEY) ?? '{}') as Record<string, string>
  } catch {
    return {}
  }
}

function speichereMerker(merker: Record<string, string>) {
  try {
    localStorage.setItem(MERKER_KEY, JSON.stringify(merker))
  } catch { /* Speicher voll/gesperrt: Anzeige nach Neuladen entfällt, Bestätigen bleibt möglich */ }
}

interface OffenerStapel {
  id: string
  nummern: string[]
  dokument: string | null
}

/** Gruppiert freigegebene Briefe, die schon in einem (noch unbestätigten) Stapel liegen. */
export function offeneStapel(
  schreiben: Schreiben[], lokal: Druckstapel[], merker: Record<string, string>,
): OffenerStapel[] {
  const je = new Map<string, OffenerStapel>()
  for (const s of schreiben) {
    if (!s.druckstapel) continue
    const eintrag = je.get(s.druckstapel) ?? { id: s.druckstapel, nummern: [], dokument: merker[s.druckstapel] ?? null }
    eintrag.nummern.push(s.nummer)
    je.set(s.druckstapel, eintrag)
  }
  for (const d of lokal) {
    if (d.status !== 'offen') continue
    je.set(d.id, {
      id: d.id, nummern: d.schreiben.map(s => s.nummer), dokument: d.dokument ?? merker[d.id] ?? null,
    })
  }
  return [...je.values()]
}

/** Druckstapel (Spec 7.3): druckbereite Briefe bündeln, Sammel-PDF prüfen, „gedruckt und kuvertiert“ bestätigen. */
export function DruckstapelPage() {
  const qc = useQueryClient()
  const [objekt, setObjekt] = useState('')
  const [auswahl, setAuswahl] = useState<Set<string>>(new Set())
  const [lokal, setLokal] = useState<Druckstapel[]>([])
  const [merker, setMerker] = useState<Record<string, string>>(ladeMerker)
  const [meldung, setMeldung] = useState<{ art: 'ok' | 'fehler'; text: string } | null>(null)
  // In dieser Sitzung bestätigte Stapel (Briefe mit noch offenem E-Mail-Anteil bleiben sonst „freigegeben“).
  const [erledigt, setErledigt] = useState<Set<string>>(new Set())

  const { data: objekte } = useQuery({ queryKey: ['objekte-sidebar'], queryFn: objekteApi.list })

  const { data: bereit, isLoading, error } = useQuery({
    queryKey: ['korrespondenz-schreiben', 'druckbereit', objekt],
    queryFn: () => schreibenApi.list({ druckbereit: '1', ...(objekt ? { objekt } : {}) }),
  })
  // Briefe, die schon in einem Stapel liegen, aber noch nicht als gedruckt bestätigt sind.
  const { data: wartend } = useQuery({
    queryKey: ['korrespondenz-schreiben', 'im-stapel'],
    queryFn: () => schreibenApi.list({ status: 'freigegeben,versand_fehlgeschlagen' }),
  })

  const stapel = useMemo(
    () => offeneStapel(wartend ?? [], lokal, merker).filter(s => !erledigt.has(s.id)),
    [wartend, lokal, merker, erledigt],
  )
  const anzahlZiel = auswahl.size > 0 ? auswahl.size : (bereit?.length ?? 0)

  const erzeugen = useMutation({
    mutationFn: () => druckstapelApi.erzeugen(
      auswahl.size > 0 ? { schreiben_ids: [...auswahl] } : objekt ? { objekt } : {},
    ),
    onMutate: () => setMeldung(null),
    onSuccess: neu => {
      setLokal(l => [neu, ...l.filter(x => x.id !== neu.id)])
      if (neu.dokument) {
        const m = { ...ladeMerker(), [neu.id]: neu.dokument }
        speichereMerker(m)
        setMerker(m)
      }
      setAuswahl(new Set())
      setMeldung({ art: 'ok', text: `Druckstapel mit ${neu.anzahl} Brief${neu.anzahl === 1 ? '' : 'en'} erzeugt.` })
      qc.invalidateQueries({ queryKey: ['korrespondenz-schreiben'] })
    },
    onError: async e => setMeldung({ art: 'fehler', text: await korrespondenzFehlerText(e, 'Druckstapel konnte nicht erzeugt werden.') }),
  })

  const bestaetigen = useMutation({
    mutationFn: (id: string) => druckstapelApi.bestaetigen(id),
    onMutate: () => setMeldung(null),
    onSuccess: (bestaetigt, id) => {
      setLokal(l => l.filter(x => x.id !== id))
      setErledigt(e => new Set(e).add(id))
      setErledigt(e => new Set(e).add(id))
      const m = { ...ladeMerker() }
      delete m[id]
      speichereMerker(m)
      setMerker(m)
      setMeldung({ art: 'ok', text: `Druckstapel bestätigt: ${bestaetigt.anzahl} Brief${bestaetigt.anzahl === 1 ? '' : 'e'} als gedruckt und kuvertiert vermerkt.` })
      qc.invalidateQueries({ queryKey: ['korrespondenz-schreiben'] })
    },
    onError: async e => setMeldung({ art: 'fehler', text: await korrespondenzFehlerText(e, 'Bestätigung nicht möglich.') }),
  })

  function umschalten(id: string) {
    setAuswahl(a => {
      const neu = new Set(a)
      if (neu.has(id)) neu.delete(id)
      else neu.add(id)
      return neu
    })
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Druckstapel</h1>
        <Link to="/korrespondenz/postausgang" className="ml-auto text-sm text-primary-600 hover:underline">Zum Postausgang</Link>
      </div>

      {meldung && (
        <div role={meldung.art === 'fehler' ? 'alert' : 'status'}
          className={`rounded border p-3 text-sm ${meldung.art === 'fehler' ? 'border-red-200 bg-red-50 text-red-700' : 'border-green-200 bg-green-50 text-green-800'}`}>
          {meldung.text}
        </div>
      )}

      {/* Druckbereite Briefe */}
      <section className="space-y-3" aria-label="Druckbereite Briefe">
        <div className="flex flex-wrap items-end gap-3">
          <h2 className="font-medium text-gray-800">Druckbereite Briefe</h2>
          <label className="text-sm ml-auto">
            <span className="block text-gray-600 mb-1">Objekt</span>
            <select value={objekt} onChange={e => { setObjekt(e.target.value); setAuswahl(new Set()) }}
              className="border border-gray-300 rounded px-2 py-1.5 text-sm">
              <option value="">Alle</option>
              {(objekte ?? []).map(o => <option key={o.id} value={o.id}>{o.objektnummer} {o.bezeichnung}</option>)}
            </select>
          </label>
          <Button type="button" disabled={anzahlZiel === 0 || erzeugen.isPending} onClick={() => erzeugen.mutate()}>
            {erzeugen.isPending ? 'Erzeuge Sammel-PDF…' : `Sammel-PDF erzeugen (${anzahlZiel})`}
          </Button>
        </div>
        <p className="text-xs text-gray-500">
          Ohne Auswahl werden alle angezeigten Briefe gebündelt (sortiert nach Objekt und Empfänger); mit Häkchen nur die gewählten.
        </p>

        {isLoading && <p className="text-gray-400">Lade Briefe…</p>}
        {error && <p role="alert" className="text-red-600">Briefe konnten nicht geladen werden.</p>}
        {bereit && (
          <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-3 py-2 w-8"><span className="sr-only">Auswahl</span></th>
                  <th className="px-3 py-2">Nummer</th>
                  <th className="px-3 py-2">Empfänger</th>
                  <th className="px-3 py-2">Objekt / Einheit</th>
                  <th className="px-3 py-2">Betreff</th>
                  <th className="px-3 py-2">Freigegeben</th>
                </tr>
              </thead>
              <tbody>
                {bereit.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-400">Keine druckbereiten Briefe.</td></tr>
                )}
                {bereit.map(s => (
                  <tr key={s.id} className="border-t border-gray-100">
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={auswahl.has(s.id)} onChange={() => umschalten(s.id)}
                        aria-label={`${s.nummer} auswählen`} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      <Link to={`/korrespondenz/postausgang/${s.id}`} className="text-primary-600 hover:underline">{s.nummer}</Link>
                    </td>
                    <td className="px-3 py-2">{s.empfaenger?.name ?? '–'}</td>
                    <td className="px-3 py-2">{s.objekt?.bezeichnung ?? '–'}{s.einheit ? ` · Einheit ${s.einheit.einheit_nr}` : ''}</td>
                    <td className="px-3 py-2">{s.betreff || '–'}</td>
                    <td className="px-3 py-2 text-gray-600">{datumZeit(s.freigegeben_am)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Erzeugte, noch nicht bestätigte Stapel */}
      <section className="space-y-3" aria-label="Offene Stapel">
        <h2 className="font-medium text-gray-800">Erzeugte Stapel — Druck bestätigen</h2>
        {stapel.length === 0 && <p className="text-sm text-gray-400">Keine offenen Stapel.</p>}
        {stapel.map(s => (
          <StapelKarte key={s.id} stapel={s} laeuft={bestaetigen.isPending}
            onBestaetigen={() => bestaetigen.mutate(s.id)} />
        ))}
      </section>
    </div>
  )
}

function StapelKarte({ stapel, laeuft, onBestaetigen }: {
  stapel: OffenerStapel; laeuft: boolean; onBestaetigen: () => void
}) {
  const [pdfOffen, setPdfOffen] = useState(false)
  const [frage, setFrage] = useState(false)
  const anzahl = stapel.nummern.length
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3" data-testid="stapel">
      <div className="flex flex-wrap items-center gap-3">
        <p className="font-medium text-gray-800">
          Stapel {stapel.id.slice(0, 8)} · {anzahl} Brief{anzahl === 1 ? '' : 'e'}
        </p>
        <p className="text-xs text-gray-500 font-mono">{stapel.nummern.join(', ')}</p>
        <div className="ml-auto flex gap-2">
          {stapel.dokument ? (
            <Button type="button" variant="secondary" onClick={() => setPdfOffen(o => !o)}>
              {pdfOffen ? 'Sammel-PDF ausblenden' : 'Sammel-PDF anzeigen'}
            </Button>
          ) : (
            <span className="text-xs text-gray-400 self-center">
              Sammel-PDF nicht mehr abrufbar (Einzel-PDFs über den Postausgang)
            </span>
          )}
          {frage ? (
            <>
              <Button type="button" disabled={laeuft} onClick={onBestaetigen}>Ja, gedruckt und kuvertiert</Button>
              <Button type="button" variant="secondary" onClick={() => setFrage(false)}>Abbrechen</Button>
            </>
          ) : (
            <Button type="button" onClick={() => setFrage(true)}>Gedruckt und kuvertiert bestätigen</Button>
          )}
        </div>
      </div>
      {pdfOffen && stapel.dokument && (
        <PdfAnzeige titel="Sammel-PDF" dateiname={`Druckstapel-${stapel.id.slice(0, 8)}.pdf`}
          laden={() => druckstapelApi.pdf(stapel.dokument!)} />
      )}
    </div>
  )
}
