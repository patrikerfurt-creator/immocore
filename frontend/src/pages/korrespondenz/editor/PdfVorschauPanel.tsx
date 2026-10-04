import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { korrespondenzFehlerText, vorlagenVersionenApi } from '../../../api/korrespondenz'
import { personenApi } from '../../../api/personen'
import { Button } from '../../../components/ui/Button'
import type { Eingabefeld, PersonList } from '../../../types'

interface Props {
  versionId: string
  eingabefelder: Eingabefeld[]
  /** Speichert ungespeicherte Änderungen, bevor die Vorschau erzeugt wird (Backend rendert den DB-Stand). */
  vorabSpeichern: () => Promise<void>
}

type Werte = Record<string, string | boolean>

/** Eingabewerte im Format des Backends: Listen als Array (eine Zeile = ein Eintrag), leere Werte entfallen. */
export function eingabewerteAufbereiten(felder: Eingabefeld[], werte: Werte): Record<string, unknown> {
  const ergebnis: Record<string, unknown> = {}
  for (const f of felder) {
    const wert = werte[f.name]
    if (f.typ === 'ja_nein') {
      if (typeof wert === 'boolean') ergebnis[f.name] = wert
    } else if (typeof wert === 'string' && wert.trim() !== '') {
      ergebnis[f.name] = f.typ === 'liste'
        ? wert.split('\n').map(z => z.trim()).filter(Boolean)
        : wert
    }
  }
  return ergebnis
}

/** PDF-Vorschau auf dem echten Briefbogen gegen einen frei wählbaren Beispiel-Eigentümer. */
export function PdfVorschauPanel({ versionId, eingabefelder, vorabSpeichern }: Props) {
  const [suche, setSuche] = useState('')
  const [person, setPerson] = useState<PersonList | null>(null)
  const [einheitId, setEinheitId] = useState('')
  const [werte, setWerte] = useState<Werte>({})
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const letzteUrl = useRef<string | null>(null)

  const { data: treffer } = useQuery({
    queryKey: ['korrespondenz-vorschau-personen', suche],
    queryFn: () => personenApi.list({ search: suche }),
    enabled: suche.trim().length >= 2 && !person,
    staleTime: 10_000,
  })

  const { data: eigentumsverhaeltnisse } = useQuery({
    queryKey: ['korrespondenz-vorschau-ev', person?.id],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ person: person!.id }),
    enabled: !!person,
  })

  // Blob-URL freigeben, sobald eine neue erzeugt wird und beim Verlassen.
  useEffect(() => () => {
    if (letzteUrl.current) URL.revokeObjectURL(letzteUrl.current)
  }, [])

  const vorschau = useMutation({
    mutationFn: async () => {
      await vorabSpeichern()
      return vorlagenVersionenApi.vorschau(versionId, {
        person_id: person!.id,
        ...(einheitId ? { einheit_id: einheitId } : {}),
        eingabewerte: eingabewerteAufbereiten(eingabefelder, werte),
      })
    },
    onMutate: () => setFehler(null),
    onSuccess: blob => {
      if (letzteUrl.current) URL.revokeObjectURL(letzteUrl.current)
      const pdf = blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' })
      const url = URL.createObjectURL(pdf)
      letzteUrl.current = url
      setPdfUrl(url)
    },
    onError: async error => {
      setPdfUrl(null)
      setFehler(await korrespondenzFehlerText(error, 'Vorschau konnte nicht erzeugt werden.'))
    },
  })

  return (
    <section className="bg-white border border-gray-200 rounded-lg p-4 space-y-3" aria-label="PDF-Vorschau">
      <h3 className="font-semibold text-gray-800">PDF-Vorschau auf dem Briefbogen</h3>

      {/* Beispiel-Eigentümer */}
      {person ? (
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{person.name}</span>
          <span className="text-gray-500">({person.personennummer})</span>
          <button type="button" className="text-primary-600 hover:underline text-xs"
            onClick={() => { setPerson(null); setEinheitId(''); setSuche('') }}>
            ändern
          </button>
        </div>
      ) : (
        <div>
          <input
            type="search"
            value={suche}
            onChange={e => setSuche(e.target.value)}
            placeholder="Beispiel-Eigentümer suchen (Name, Nummer)…"
            aria-label="Beispiel-Eigentümer suchen"
            className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          />
          {treffer && treffer.length > 0 && (
            <ul className="border border-gray-200 rounded mt-1 max-h-40 overflow-auto text-sm" aria-label="Personen-Treffer">
              {treffer.slice(0, 20).map(p => (
                <li key={p.id}>
                  <button type="button" className="w-full text-left px-2 py-1 hover:bg-gray-50"
                    onClick={() => setPerson(p)}>
                    {p.name} <span className="text-gray-400">({p.personennummer})</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {person && (eigentumsverhaeltnisse?.length ?? 0) > 0 && (
        <label className="block text-sm">
          <span className="text-gray-700">Einheit (optional)</span>
          <select value={einheitId} onChange={e => setEinheitId(e.target.value)}
            className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
            <option value="">— keine —</option>
            {eigentumsverhaeltnisse!.map(ev => (
              <option key={ev.id} value={ev.einheit}>
                Einheit {ev.einheit_nr}{ev.ende ? ' (beendet)' : ''}
              </option>
            ))}
          </select>
        </label>
      )}

      {/* Beispielwerte der Eingabefelder */}
      {eingabefelder.filter(f => f.name).length > 0 && (
        <fieldset className="border border-gray-200 rounded p-2 space-y-2">
          <legend className="text-xs text-gray-500 px-1">Beispielwerte für Eingabefelder</legend>
          {eingabefelder.filter(f => f.name).map(f => (
            <label key={f.name} className="block text-sm">
              <span className="text-gray-700">{f.label || f.name}{f.pflicht ? ' *' : ''}</span>
              {f.typ === 'ja_nein' ? (
                <input type="checkbox" className="ml-2"
                  checked={werte[f.name] === true}
                  onChange={e => setWerte(w => ({ ...w, [f.name]: e.target.checked }))} />
              ) : f.typ === 'mehrzeilig' || f.typ === 'liste' ? (
                <textarea rows={3} value={(werte[f.name] as string) ?? ''}
                  placeholder={f.typ === 'liste' ? 'Ein Eintrag pro Zeile' : ''}
                  onChange={e => setWerte(w => ({ ...w, [f.name]: e.target.value }))}
                  className="mt-1 w-full border border-gray-300 rounded px-2 py-1" />
              ) : (
                <input
                  type={f.typ === 'datum' ? 'date' : f.typ === 'uhrzeit' ? 'time' : 'text'}
                  value={(werte[f.name] as string) ?? ''}
                  placeholder={f.typ === 'betrag' ? '1234,56' : ''}
                  onChange={e => setWerte(w => ({ ...w, [f.name]: e.target.value }))}
                  className="mt-1 w-full border border-gray-300 rounded px-2 py-1" />
              )}
            </label>
          ))}
        </fieldset>
      )}

      <Button type="button" disabled={!person || vorschau.isPending} onClick={() => vorschau.mutate()}>
        {vorschau.isPending ? 'Erzeuge Vorschau…' : 'Vorschau erzeugen'}
      </Button>
      <p className="text-xs text-gray-500">Ungespeicherte Änderungen werden vorher automatisch gespeichert.</p>

      {fehler && <p role="alert" className="text-sm text-red-600">{fehler}</p>}
      {pdfUrl && (
        <iframe title="PDF-Vorschau" src={pdfUrl} className="w-full h-[75vh] border border-gray-300 rounded" />
      )}
    </section>
  )
}
