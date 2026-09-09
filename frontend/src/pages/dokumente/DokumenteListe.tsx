import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { dokumenteApi } from '../../api/dokumente'
import { objekteApi } from '../../api/objekte'
import { Button } from '../../components/ui/Button'
import type { Dokument } from '../../types'

const KATEGORIEN = ['allgemein', 'vertrag', 'rechnung', 'protokoll', 'beschluss', 'korrespondenz', 'sonstiges']

// Sortierbare Spalten der Belegübersicht (API-Vertrag v1.0, Abschnitt "Sortierung").
type SortFeld = 'rechnung__rechnungsdatum' | 'rechnung__betrag_brutto'
type Ordering = SortFeld | `-${SortFeld}`

function formatDatum(iso: string | null): string {
  if (!iso) return '–'
  return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function formatBetrag(brutto: string | null): string {
  if (brutto === null) return '–'
  const zahl = Number(brutto)
  if (Number.isNaN(zahl)) return '–'
  return `${zahl.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
}

/** Fünf Belegspalten (Kreditor … Eingangsdatum) einer Tabellenzeile.
 * Ohne Rechnungsbezug (alle Felder null) werden sie zu einer leeren Zelle
 * zusammengefasst statt fünf verwirrenden „–"-Platzhaltern (Spec Abschnitt 6). */
function BelegSpalten({ d }: { d: Dokument }) {
  const ohneRechnungsbezug =
    d.rechnungsdatum === null &&
    d.eingangsdatum === null &&
    d.kreditor_name === null &&
    d.kreditor_unbestaetigt === null &&
    d.betrag_brutto === null &&
    d.kurztext === null

  if (ohneRechnungsbezug) {
    return <td colSpan={5} className="px-4 py-3" />
  }

  return (
    <>
      <td className="px-4 py-3 text-gray-600">
        {d.kreditor_name ?? '–'}
        {d.kreditor_unbestaetigt === true && (
          <span
            className="ml-1 text-amber-500"
            title="Kreditor nicht eindeutig zugeordnet – Name aus Rechnungstext, kein Stammdatensatz"
          >
            ⚠
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-gray-600" title={d.kurztext_volltext ?? undefined}>
        {d.kurztext ?? '–'}
      </td>
      <td className="px-4 py-3 text-right text-gray-600">{formatBetrag(d.betrag_brutto)}</td>
      <td className="px-4 py-3 text-gray-600">{formatDatum(d.rechnungsdatum)}</td>
      <td className="px-4 py-3 text-gray-600">{formatDatum(d.eingangsdatum)}</td>
    </>
  )
}

export function DokumenteListe() {
  const [searchParams] = useSearchParams()
  const [objektId, setObjektId] = useState(searchParams.get('objekt') ?? '')
  const [kategorie, setKategorie] = useState('')
  const [uploadObjektId, setUploadObjektId] = useState('')
  const [uploadKategorie, setUploadKategorie] = useState('allgemein')
  const [beschreibung, setBeschreibung] = useState('')
  const [ordering, setOrdering] = useState<Ordering | ''>('')
  const fileRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: dokumente, isLoading } = useQuery({
    queryKey: ['dokumente', objektId, kategorie, ordering],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektId) params.objekt = objektId
      if (kategorie) params.kategorie = kategorie
      if (ordering) params.ordering = ordering
      return dokumenteApi.list(params)
    },
  })

  function toggleOrdering(feld: SortFeld) {
    setOrdering(prev => (prev === feld ? `-${feld}` : feld))
  }

  function sortIndikator(feld: SortFeld): string {
    if (ordering === feld) return ' ▲'
    if (ordering === `-${feld}`) return ' ▼'
    return ''
  }

  const uploadMutation = useMutation({
    mutationFn: ({ file }: { file: File }) =>
      dokumenteApi.upload(uploadObjektId, file, uploadKategorie, beschreibung),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dokumente'] })
      if (fileRef.current) fileRef.current.value = ''
      setBeschreibung('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => dokumenteApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dokumente'] }),
  })

  function handleUpload() {
    const file = fileRef.current?.files?.[0]
    if (!file || !uploadObjektId) return
    uploadMutation.mutate({ file })
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Dokumente</h1>

      <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6">
        <h2 className="font-semibold text-gray-700 mb-3">Dokument hochladen</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Objekt</label>
            <select
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={uploadObjektId}
              onChange={e => setUploadObjektId(e.target.value)}
            >
              <option value="">Objekt wählen…</option>
              {objekte?.map(o => (
                <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Kategorie</label>
            <select
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={uploadKategorie}
              onChange={e => setUploadKategorie(e.target.value)}
            >
              {KATEGORIEN.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Beschreibung</label>
            <input
              type="text"
              value={beschreibung}
              onChange={e => setBeschreibung(e.target.value)}
              className="rounded border border-gray-300 px-3 py-2 text-sm w-48"
              placeholder="Optional…"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Datei</label>
            <input ref={fileRef} type="file" className="text-sm" />
          </div>
          <Button onClick={handleUpload} disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? 'Lädt…' : 'Hochladen'}
          </Button>
        </div>
      </div>

      <div className="flex gap-3 mb-4">
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={objektId}
          onChange={e => setObjektId(e.target.value)}
        >
          <option value="">Alle Objekte</option>
          {objekte?.map(o => (
            <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
          ))}
        </select>
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={kategorie}
          onChange={e => setKategorie(e.target.value)}
        >
          <option value="">Alle Kategorien</option>
          {KATEGORIEN.map(k => <option key={k} value={k}>{k}</option>)}
        </select>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Kreditor</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Kurztext</th>
                <th
                  className="text-right px-4 py-3 font-medium text-gray-600 cursor-pointer select-none"
                  onClick={() => toggleOrdering('rechnung__betrag_brutto')}
                >
                  Bruttobetrag{sortIndikator('rechnung__betrag_brutto')}
                </th>
                <th
                  className="text-left px-4 py-3 font-medium text-gray-600 cursor-pointer select-none"
                  onClick={() => toggleOrdering('rechnung__rechnungsdatum')}
                >
                  Rechnungsdatum{sortIndikator('rechnung__rechnungsdatum')}
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Eingangsdatum</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Kategorie</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Beschreibung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Hochgeladen am</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {dokumente?.map(d => (
                <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <BelegSpalten d={d} />
                  <td className="px-4 py-3 text-gray-600">{d.kategorie}</td>
                  <td className="px-4 py-3 text-gray-600">{d.beschreibung || '–'}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {formatDatum(d.hochgeladen_am)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {/* Auslieferung über /dokumente/{id}/datei/ — der direkte MEDIA-Link
                        greift nicht, wenn ablage_wurzel='rechnungen' ist. */}
                    <button
                      onClick={() => dokumenteApi.openDatei(d.id)}
                      className="text-xs text-primary-600 hover:underline"
                      title={d.dateiname}
                    >
                      Öffnen
                    </button>
                    <button
                      onClick={() => {
                        if (!d.loeschbar) return
                        deleteMutation.mutate(d.id)
                      }}
                      disabled={!d.loeschbar}
                      title={!d.loeschbar ? (d.loeschsperre_grund ?? undefined) : undefined}
                      className={
                        d.loeschbar
                          ? 'ml-3 text-xs text-red-600 hover:underline'
                          : 'ml-3 text-xs text-gray-400 cursor-not-allowed'
                      }
                    >
                      Löschen
                    </button>
                  </td>
                </tr>
              ))}
              {dokumente?.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                    Keine Dokumente gefunden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
