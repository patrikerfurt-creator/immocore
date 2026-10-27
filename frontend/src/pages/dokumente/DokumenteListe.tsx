import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { dokumenteApi, type UploadVorschlag } from '../../api/dokumente'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'
import { aktenApi, type Aktenart } from '../../api/akten'
import { Button } from '../../components/ui/Button'
import type { Dokument } from '../../types'

const KATEGORIEN = ['allgemein', 'vertrag', 'rechnung', 'protokoll', 'beschluss', 'korrespondenz', 'sonstiges']

// Dokumenttypen (Dokument.TYP_CHOICES im Backend) — steuert u.a. den
// regelbasierten Registervorschlag.
const DOKUMENT_TYPEN: { wert: string; label: string }[] = [
  { wert: 'sonstiges', label: 'Sonstiges' },
  { wert: 'beleg', label: 'Beleg' },
  { wert: 'vertrag', label: 'Vertrag' },
  { wert: 'korrespondenz', label: 'Korrespondenz' },
  { wert: 'beschluss', label: 'Beschluss' },
  { wert: 'abrechnung', label: 'Abrechnung' },
]

// Owner-Ebene (Owner-Regel: genau eine von Objekt/Einheit/Person).
type Ebene = 'objekt' | 'einheit' | 'person'
const EBENEN: { wert: Ebene; label: string }[] = [
  { wert: 'objekt', label: 'Objekt' },
  { wert: 'einheit', label: 'Einheit' },
  { wert: 'person', label: 'Person' },
]
const AKTENART_JE_EBENE: Record<Ebene, Aktenart> = {
  objekt: 'haus',
  einheit: 'wohnung',
  person: 'eigentuemer',
}

function prozent(konfidenz: number | null): string {
  return konfidenz === null ? '' : ` · ${Math.round(konfidenz * 100)} %`
}

/** Lesbare Fehlermeldung aus einem fehlgeschlagenen Upload (DRF-Feldfehler
 *  oder freie Fehlermeldung). */
function uploadFehlertext(err: unknown): string {
  const daten = (err as { response?: { data?: unknown } })?.response?.data
  if (daten && typeof daten === 'object') {
    if ('error' in daten && typeof (daten as { error: unknown }).error === 'string') {
      return (daten as { error: string }).error
    }
    const felder = Object.entries(daten as Record<string, unknown>)
      .map(([feld, wert]) => `${feld}: ${Array.isArray(wert) ? wert.join(' ') : String(wert)}`)
    if (felder.length) return felder.join(' · ')
  }
  return 'Der Upload ist fehlgeschlagen.'
}

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
 * Ohne Rechnungsbezug (alle Felder null) werden sie zu EINER Zelle zusammengefasst
 * statt fünf verwirrenden „–"-Platzhaltern (Spec Abschnitt 6). Dort steht dann der
 * Dateiname: Verträge, Beschlüsse und Korrespondenz haben sonst keinen sichtbaren
 * Identifikator mehr, seit die Dateiname-Spalte entfallen ist. Für Belege bleibt er
 * ausgeblendet — die stehen mit Kreditor, Betrag und Kurztext für sich. */
function BelegSpalten({ d }: { d: Dokument }) {
  const ohneRechnungsbezug =
    d.rechnungsdatum === null &&
    d.eingangsdatum === null &&
    d.kreditor_name === null &&
    d.kreditor_unbestaetigt === null &&
    d.betrag_brutto === null &&
    d.kurztext === null

  if (ohneRechnungsbezug) {
    return (
      <td colSpan={5} className="px-4 py-3 text-gray-500">
        {d.dateiname}
      </td>
    )
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

/** Zeigt die automatischen Vorschläge an (Kontext + Register) — rein
 *  informativ; die Felder sind bereits vorbelegt, bestätigt wird durch den
 *  Nutzer über den Hochladen-Button. */
function VorschlagHinweis({ v }: { v: UploadVorschlag }) {
  const k = v.kontext
  const kontextLabel = k.owner === 'objekt' ? k.objekt?.label
    : k.owner === 'einheit' ? k.einheit?.label
    : k.owner === 'person' ? k.person?.label : null

  return (
    <div className="mb-3 rounded border border-primary-200 bg-primary-50 px-3 py-2 text-sm">
      <div className="font-medium text-primary-800 mb-0.5">
        Automatischer Vorschlag · bitte prüfen und bestätigen
      </div>
      {kontextLabel ? (
        <div className="text-gray-700">
          Zuordnung: <strong>{kontextLabel}</strong>{' '}
          <span className="text-gray-500">({k.quelle}{prozent(k.konfidenz)})</span>
          {k.begruendung && <span className="text-gray-500"> – {k.begruendung}</span>}
        </div>
      ) : (
        <div className="text-gray-500">
          Keine sichere Zuordnung{k.begruendung ? ` – ${k.begruendung}` : ''}.
        </div>
      )}
      {v.register.register_id ? (
        <div className="text-gray-700">
          Register: <strong>{v.register.code} {v.register.bezeichnung}</strong>{' '}
          <span className="text-gray-500">({v.register.quelle}{prozent(v.register.konfidenz)})</span>
        </div>
      ) : (
        v.register.begruendung && (
          <div className="text-gray-500">Register: {v.register.begruendung}</div>
        )
      )}
      {!v.inhalt_erkannt && (
        <div className="text-amber-600">
          Kein lesbarer Textinhalt – Vorschlag nur aus dem Dateinamen.
        </div>
      )}
      {(k.fehler || v.register.fehler) && (
        <div className="text-red-600">{k.fehler || v.register.fehler}</div>
      )}
    </div>
  )
}

export function DokumenteListe() {
  const [searchParams] = useSearchParams()
  const [objektId, setObjektId] = useState(searchParams.get('objekt') ?? '')
  const [kategorie, setKategorie] = useState('')
  const [uploadKategorie, setUploadKategorie] = useState('allgemein')
  const [beschreibung, setBeschreibung] = useState('')
  const [ordering, setOrdering] = useState<Ordering | ''>('')

  // Upload-Zuordnung (vorbelegt aus dem Vorschlag, vom Nutzer bestätigt)
  const [ebene, setEbene] = useState<Ebene>('objekt')
  const [uploadObjektId, setUploadObjektId] = useState('')
  const [uploadEinheitId, setUploadEinheitId] = useState('')
  const [uploadPersonId, setUploadPersonId] = useState('')
  const [registerId, setRegisterId] = useState('')
  const [dokumentTyp, setDokumentTyp] = useState('sonstiges')
  const [vorschlag, setVorschlag] = useState<UploadVorschlag | null>(null)

  const fileRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: einheiten } = useQuery({
    queryKey: ['einheiten', uploadObjektId],
    queryFn: () => objekteApi.listEinheiten({ objekt: uploadObjektId }),
    enabled: ebene === 'einheit' && !!uploadObjektId,
  })
  const { data: personen } = useQuery({
    queryKey: ['personen'],
    queryFn: () => personenApi.list(),
    enabled: ebene === 'person',
  })
  const { data: registerAlle } = useQuery({
    queryKey: ['aktenregister', ebene],
    queryFn: () => aktenApi.registerListe(AKTENART_JE_EBENE[ebene]),
  })
  // Gemeinsame Gliederung plus die Untergliederung des gewählten Objekts.
  const registerAuswahl = (registerAlle ?? []).filter(
    r => r.objekt === null || r.objekt === uploadObjektId,
  )
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

  // Übernimmt die automatischen Vorschläge in die Auswahlfelder — gesetzt wird
  // nichts, der Nutzer bestätigt oder ändert sie vor dem Hochladen.
  function uebernehmeVorschlag(v: UploadVorschlag) {
    const k = v.kontext
    if (k.owner) {
      setEbene(k.owner)
      if (k.owner === 'objekt' && k.objekt) setUploadObjektId(k.objekt.id)
      if (k.owner === 'person' && k.person) setUploadPersonId(k.person.id)
      if (k.owner === 'einheit' && k.einheit) {
        if (k.einheit.objekt) setUploadObjektId(k.einheit.objekt)
        setUploadEinheitId(k.einheit.id)
      }
    } else if (k.objekt) {
      // Keine sichere Zuordnung, aber ein Objektkandidat — als Startpunkt.
      setUploadObjektId(k.objekt.id)
    }
    if (v.register.register_id) setRegisterId(v.register.register_id)
  }

  const analyseMutation = useMutation({
    mutationFn: (file: File) =>
      dokumenteApi.analyseVorschlag(file, beschreibung, dokumentTyp),
    onSuccess: (v) => {
      setVorschlag(v)
      uebernehmeVorschlag(v)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ file }: { file: File }) =>
      dokumenteApi.upload(file, {
        objekt: ebene === 'objekt' ? uploadObjektId : null,
        einheit: ebene === 'einheit' ? uploadEinheitId : null,
        person: ebene === 'person' ? uploadPersonId : null,
        register: registerId || null,
        kategorie: uploadKategorie,
        dokument_typ: dokumentTyp,
        beschreibung,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dokumente'] })
      if (fileRef.current) fileRef.current.value = ''
      setBeschreibung('')
      setVorschlag(null)
      setUploadEinheitId('')
      setUploadPersonId('')
      setRegisterId('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => dokumenteApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dokumente'] }),
  })

  // Welcher Owner ist aktuell gewählt (abhängig von der Ebene)?
  const ownerId = ebene === 'objekt' ? uploadObjektId
    : ebene === 'einheit' ? uploadEinheitId : uploadPersonId

  function handleFileChange() {
    setVorschlag(null)
    const file = fileRef.current?.files?.[0]
    if (!file) return
    analyseMutation.mutate(file)
  }

  function handleUpload() {
    const file = fileRef.current?.files?.[0]
    if (!file || !ownerId) return
    uploadMutation.mutate({ file })
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Dokumente</h1>

      <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6">
        <h2 className="font-semibold text-gray-700 mb-3">Dokument hochladen</h2>

        {/* Schritt 1: Datei wählen → es wird automatisch analysiert */}
        <div className="flex flex-wrap gap-3 items-center mb-3">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Datei</label>
            <input ref={fileRef} type="file" className="text-sm" onChange={handleFileChange} />
          </div>
          {analyseMutation.isPending && (
            <span className="text-sm text-gray-500">Analysiere Inhalt…</span>
          )}
          {analyseMutation.isError && (
            <span className="text-sm text-amber-600">
              Analyse fehlgeschlagen – bitte Zuordnung manuell wählen.
            </span>
          )}
        </div>

        {/* Schritt 2: Vorschlag (vorbelegt, zur Bestätigung) */}
        {vorschlag && <VorschlagHinweis v={vorschlag} />}

        {/* Schritt 3: Zuordnung prüfen/ändern und hochladen */}
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Zuordnen zu</label>
            <div className="flex rounded border border-gray-300 overflow-hidden">
              {EBENEN.map(e => (
                <button
                  key={e.wert}
                  type="button"
                  onClick={() => setEbene(e.wert)}
                  className={
                    ebene === e.wert
                      ? 'px-3 py-2 text-sm bg-primary-600 text-white'
                      : 'px-3 py-2 text-sm bg-white text-gray-600 hover:bg-gray-50'
                  }
                >
                  {e.label}
                </button>
              ))}
            </div>
          </div>

          {ebene !== 'person' && (
            <div>
              <label className="text-xs text-gray-500 block mb-1">Objekt</label>
              <select
                className="rounded border border-gray-300 px-3 py-2 text-sm"
                value={uploadObjektId}
                onChange={e => { setUploadObjektId(e.target.value); setUploadEinheitId('') }}
              >
                <option value="">Objekt wählen…</option>
                {objekte?.map(o => (
                  <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
                ))}
              </select>
            </div>
          )}

          {ebene === 'einheit' && (
            <div>
              <label className="text-xs text-gray-500 block mb-1">Einheit</label>
              <select
                className="rounded border border-gray-300 px-3 py-2 text-sm"
                value={uploadEinheitId}
                onChange={e => setUploadEinheitId(e.target.value)}
                disabled={!uploadObjektId}
              >
                <option value="">{uploadObjektId ? 'Einheit wählen…' : 'Erst Objekt wählen'}</option>
                {einheiten?.map(ein => (
                  <option key={ein.id} value={ein.id}>{ein.einheit_nr} – {ein.lage}</option>
                ))}
              </select>
            </div>
          )}

          {ebene === 'person' && (
            <div>
              <label className="text-xs text-gray-500 block mb-1">Person</label>
              <select
                className="rounded border border-gray-300 px-3 py-2 text-sm"
                value={uploadPersonId}
                onChange={e => setUploadPersonId(e.target.value)}
              >
                <option value="">Person wählen…</option>
                {personen?.map(p => (
                  <option key={p.id} value={p.id}>{p.personennummer} – {p.name}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="text-xs text-gray-500 block mb-1">Register</label>
            <select
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={registerId}
              onChange={e => setRegisterId(e.target.value)}
            >
              <option value="">Ohne Register</option>
              {registerAuswahl.map(r => (
                <option key={r.id} value={r.id}>{r.code} {r.bezeichnung}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-gray-500 block mb-1">Dokumenttyp</label>
            <select
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={dokumentTyp}
              onChange={e => setDokumentTyp(e.target.value)}
            >
              {DOKUMENT_TYPEN.map(t => <option key={t.wert} value={t.wert}>{t.label}</option>)}
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

          <Button onClick={handleUpload} disabled={uploadMutation.isPending || !ownerId}>
            {uploadMutation.isPending ? 'Lädt…' : 'Hochladen'}
          </Button>
        </div>

        {!ownerId && (
          <div className="mt-2 text-sm text-gray-500">
            Bitte ein Objekt, eine Einheit oder eine Person wählen, um hochzuladen.
          </div>
        )}
        {uploadMutation.isError && (
          <div className="mt-2 text-sm text-red-600">
            {uploadFehlertext(uploadMutation.error)}
          </div>
        )}
        {uploadMutation.isSuccess && (
          <div className="mt-2 text-sm text-green-700">Dokument hochgeladen.</div>
        )}
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
