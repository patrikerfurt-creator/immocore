import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { vorgaengeApi } from '../../api/vorgaenge'
import { mitarbeiterApi } from '../../api/mitarbeiter'
import { handwerkerApi } from '../../api/handwerker'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type {
  HandwerkerauftragCreatePayload, HandwerkerauftragDetail, Kreditor, VorgangDetail as VorgangDetailTyp,
  VorgangPrioritaet, VorgangStatus,
} from '../../types'
import { HWA_STATUS_LABEL, fehlerText as hwaFehlerText } from '../handwerker/shared'

// Freundliche Fehlermeldung aus einer Axios-Fehlerantwort extrahieren
// (Backend liefert bei 400 entweder {detail: ...} oder Feldfehler {feld: [...]}).
function fehlerText(error: unknown, fallback: string): string {
  // @ts-expect-error axios error shape
  const data = error?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return String(data.detail)
  const werte = Object.values(data as Record<string, unknown>).flat()
  return werte.length > 0 ? werte.join(' ') : fallback
}

// Spiegel der Übergangstabelle aus vorgang_service._ERLAUBTE_UEBERGAENGE
// (Spec Kap. 1.3) — einfache, wartbare Variante statt eines eigenen
// Backend-Endpoints, der dieselbe Information liefern müsste.
const ERLAUBTE_UEBERGAENGE: Record<VorgangStatus, VorgangStatus[]> = {
  offen: ['in_bearbeitung', 'storniert'],
  in_bearbeitung: ['wartet_extern', 'wiedervorlage', 'erledigt', 'storniert'],
  wartet_extern: ['in_bearbeitung', 'erledigt', 'storniert'],
  wiedervorlage: ['in_bearbeitung', 'storniert'],
  erledigt: ['in_bearbeitung'],
  storniert: [],
}

const STATUS_LABEL: Record<VorgangStatus, string> = {
  offen: 'Offen',
  in_bearbeitung: 'In Bearbeitung',
  wartet_extern: 'Wartet auf Dritte',
  wiedervorlage: 'Wiedervorlage',
  erledigt: 'Erledigt',
  storniert: 'Storniert',
}

const EREIGNIS_LABEL: Record<string, string> = {
  kommentar: 'Kommentar',
  statuswechsel: 'Statuswechsel',
  zuweisung_geaendert: 'Zuweisung geändert',
  dokument_verknuepft: 'Dokument verknüpft',
  system_wiedervorlage_faellig: 'System: Wiedervorlage fällig',
  antwort_vorschlag_erzeugt: 'KI-Antwortvorschlag erzeugt',
  antwort_vorschlag_bearbeitet: 'Antwortvorschlag bearbeitet',
  antwort_vorschlag_freigegeben: 'Antwortvorschlag freigegeben',
  antwort_vorschlag_verworfen: 'Antwortvorschlag verworfen',
  handwerker_beauftragt: 'Handwerker beauftragt',
  handwerker_angenommen: 'Handwerker: Auftrag angenommen',
  handwerker_abgelehnt: 'Handwerker: Auftrag abgelehnt',
  handwerker_abgeschlossen: 'Handwerker: Auftrag abgeschlossen',
  handwerker_abgelaufen: 'Handwerker: Auftragsbestätigung abgelaufen',
}

// Vorgang gilt als „gerade erst angelegt“, solange auto-generierte Vorschläge
// per Celery typischerweise fertig sein sollten — nur für den UI-Hinweis relevant.
const GERADE_ERSTELLT_SCHWELLE_MS = 15 * 60 * 1000

function DATUM(s: string | null) {
  return s ? new Date(s).toLocaleString('de-DE') : '–'
}

function KreditorZeile({
  kreditor, hausfirma, ausgewaehlt, onSelect,
}: { kreditor: Kreditor; hausfirma: boolean; ausgewaehlt: boolean; onSelect: () => void }) {
  const hatEmail = !!kreditor.email
  return (
    <button
      type="button"
      disabled={!hatEmail}
      onClick={onSelect}
      className={`w-full text-left px-3 py-2 text-sm border-b border-gray-100 last:border-0 flex items-center justify-between transition-colors ${
        ausgewaehlt ? 'bg-primary-50' : hatEmail ? 'hover:bg-gray-50' : 'opacity-50 cursor-not-allowed'
      }`}
    >
      <span>
        {kreditor.name}
        {hausfirma && <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-primary-100 text-primary-700">Hausfirma</span>}
        {kreditor.gewerke_bezeichnungen.length > 0 && (
          <span className="ml-2 text-xs text-gray-400">({kreditor.gewerke_bezeichnungen.join(', ')})</span>
        )}
      </span>
      {!hatEmail && <span className="text-xs text-red-500">E-Mail fehlt am Kreditor</span>}
      {ausgewaehlt && <span className="text-xs text-primary-600">✓ ausgewählt</span>}
    </button>
  )
}

// Anlage von Handwerkeraufträgen aus einem Vorgang heraus (Phase D).
//
// Abweichung/Limitation (siehe Abschlussbericht): das Bereits-Existierende-
// Aufträge-Verzeichnis ist ein Best-effort — GET /handwerkerauftraege/ kennt
// keinen "vorgang"-Filter und der List-Serializer liefert kein "vorgang"-Feld
// (nur der Detail-Serializer). handwerkerApi.ladeFuerVorgang() funktioniert
// deshalb nur, wenn der Vorgang direkt ein Objekt hat (lädt objekt-gefiltert,
// matcht dann je Treffer per Detail-Aufruf). Für Vorgänge ohne direkten
// Objektbezug (nur Einheit oder nur Person) werden hier nur die in dieser
// Sitzung neu angelegten Aufträge angezeigt.
function HandwerkerBeauftragenSection({ vorgang }: { vorgang: VorgangDetailTyp }) {
  const qc = useQueryClient()
  const [offen, setOffen] = useState(false)
  const [gewerkFilter, setGewerkFilter] = useState('')
  const [kreditorId, setKreditorId] = useState('')
  const [objektId, setObjektId] = useState(vorgang.objekt ?? '')
  const [titel, setTitel] = useState('')
  const [beschreibung, setBeschreibung] = useState('')
  const [gewuenschtAb, setGewuenschtAb] = useState('')
  const [prioritaet, setPrioritaet] = useState<VorgangPrioritaet>(vorgang.prioritaet)
  const [geschaetzteKosten, setGeschaetzteKosten] = useState('')
  const [neuAngelegt, setNeuAngelegt] = useState<HandwerkerauftragDetail[]>([])
  const [erfolg, setErfolg] = useState<HandwerkerauftragDetail | null>(null)

  const brauchtObjektAuswahl = !vorgang.objekt && !vorgang.einheit
  const objektFuerHandwerkerFilter = objektId || vorgang.objekt || ''

  const { data: gewerke } = useQuery({
    queryKey: ['gewerke'], queryFn: handwerkerApi.gewerke, enabled: offen,
  })
  const { data: objekte } = useQuery({
    queryKey: ['objekte'], queryFn: objekteApi.list, enabled: offen && brauchtObjektAuswahl,
  })
  // Unfiltert (ohne Gewerk-Filter) laden, damit der Leerzustand unterscheiden
  // kann zwischen "gar keine Handwerker gepflegt" und "keine Treffer für das
  // gewählte Gewerk" — der Gewerk-Filter wird clientseitig angewendet.
  const { data: hausHandwerkerRoh } = useQuery({
    queryKey: ['handwerker-hausfirmen', objektFuerHandwerkerFilter],
    queryFn: () => handwerkerApi.kreditorenHandwerker({ objekt: objektFuerHandwerkerFilter }),
    enabled: offen && !!objektFuerHandwerkerFilter,
  })
  const { data: alleHandwerkerRoh } = useQuery({
    queryKey: ['handwerker-alle'],
    queryFn: () => handwerkerApi.kreditorenHandwerker(),
    enabled: offen,
  })

  const { data: bestehendeAuftraege } = useQuery({
    queryKey: ['vorgang-handwerkerauftraege', vorgang.id, vorgang.objekt],
    queryFn: () => handwerkerApi.ladeFuerVorgang(vorgang.id, vorgang.objekt!),
    enabled: !!vorgang.objekt,
  })

  const nachGewerkGefiltert = (liste: Kreditor[]) =>
    gewerkFilter ? liste.filter(k => k.gewerke.includes(gewerkFilter)) : liste

  const hausListe = nachGewerkGefiltert(hausHandwerkerRoh ?? [])
  const hausIds = new Set(hausListe.map(k => k.id))
  const uebrigeListe = nachGewerkGefiltert(alleHandwerkerRoh ?? []).filter(k => !hausIds.has(k.id))
  const alleSichtbaren = [...hausListe, ...uebrigeListe]
  const ausgewaehlterKreditor = alleSichtbaren.find(k => k.id === kreditorId)

  // Für den Leerzustand: unterscheide "gar kein Kreditor ist als Handwerker
  // markiert" von "keine Treffer für den gewählten Gewerk-Filter" (Grund,
  // warum Patrik den Dialog zunächst für defekt hielt).
  const gibtEsUeberhauptHandwerker = (alleHandwerkerRoh ?? []).length > 0

  const createMutation = useMutation({
    mutationFn: () => {
      const payload: HandwerkerauftragCreatePayload = {
        kreditor: kreditorId,
        titel,
        beschreibung: beschreibung || undefined,
        gewuenscht_ab: gewuenschtAb || undefined,
        prioritaet,
        geschaetzte_kosten: geschaetzteKosten || undefined,
      }
      if (brauchtObjektAuswahl) payload.objekt = objektId
      return handwerkerApi.erstelleAusVorgang(vorgang.id, payload)
    },
    onSuccess: (auftrag) => {
      setNeuAngelegt(prev => [auftrag, ...prev])
      setErfolg(auftrag)
      if (vorgang.objekt) qc.invalidateQueries({ queryKey: ['vorgang-handwerkerauftraege', vorgang.id, vorgang.objekt] })
    },
  })

  function dialogOeffnen() {
    setTitel(vorgang.betreff)
    setBeschreibung(vorgang.beschreibung ?? '')
    setPrioritaet(vorgang.prioritaet)
    setObjektId(vorgang.objekt ?? '')
    setKreditorId('')
    setGewerkFilter('')
    setGewuenschtAb('')
    setGeschaetzteKosten('')
    setErfolg(null)
    setOffen(true)
  }

  const alleListe = [...neuAngelegt, ...(bestehendeAuftraege ?? [])].filter(
    (a, idx, arr) => arr.findIndex(x => x.id === a.id) === idx,
  )
  const kannAbsenden = !!kreditorId && !!titel.trim() && (!brauchtObjektAuswahl || !!objektId)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-medium text-gray-800">Handwerkeraufträge</h2>
        {!offen && <Button size="sm" onClick={dialogOeffnen}>+ Handwerker beauftragen</Button>}
      </div>

      {alleListe.length === 0 ? (
        <p className="text-sm text-gray-400 mb-2">Noch kein Handwerkerauftrag zu diesem Vorgang.</p>
      ) : (
        <ul className="divide-y divide-gray-100 mb-2">
          {alleListe.map(a => (
            <li key={a.id} className="py-2 text-sm flex items-center justify-between">
              <span>
                <Link to={`/handwerker/auftraege/${a.id}`} className="text-primary-600 hover:underline font-mono text-xs mr-2">
                  {a.nummer}
                </Link>
                {a.titel} — {a.kreditor_name}
              </span>
              <Badge value={a.status} label={HWA_STATUS_LABEL[a.status]} />
            </li>
          ))}
        </ul>
      )}

      {!vorgang.objekt && (
        <p className="text-xs text-gray-400">
          Hinweis: bestehende Handwerkeraufträge zu diesem Vorgang werden hier nur zuverlässig aufgelistet,
          solange der Vorgang direkt ein Objekt hat — neu in dieser Sitzung angelegte erscheinen aber immer sofort oben.
        </p>
      )}

      {offen && (
        <div className="mt-4 border-t border-gray-100 pt-4 space-y-3">
          {erfolg ? (
            <div className="bg-green-50 border border-green-200 rounded p-3 text-sm">
              <p className="text-green-800 font-medium mb-1">Auftrag {erfolg.nummer} wurde angelegt.</p>
              <p className="text-green-700">Die Auftragsmail an den Handwerker wird im Hintergrund versendet.</p>
              <Link to={`/handwerker/auftraege/${erfolg.id}`} className="text-primary-600 hover:underline text-xs mt-1 inline-block">
                Zum Auftrag →
              </Link>
              <div className="mt-2">
                <Button size="sm" variant="secondary" onClick={() => setOffen(false)}>Schließen</Button>
              </div>
            </div>
          ) : (
            <>
              {brauchtObjektAuswahl && (
                <div>
                  <label className="text-sm font-medium text-gray-700 block mb-1">Objekt *</label>
                  <select
                    className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                    value={objektId}
                    onChange={e => { setObjektId(e.target.value); setKreditorId('') }}
                  >
                    <option value="">Objekt wählen…</option>
                    {objekte?.map(o => (
                      <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-400 mt-1">
                    Dieser Vorgang hat keinen Objektbezug — ohne Objekt lehnt das Backend die Anlage ab.
                  </p>
                </div>
              )}

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Gewerk (Filter)</label>
                <select
                  className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                  value={gewerkFilter}
                  onChange={e => setGewerkFilter(e.target.value)}
                >
                  <option value="">Alle Gewerke</option>
                  {gewerke?.map(g => (
                    <option key={g.id} value={g.id}>{g.bezeichnung}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Handwerker *</label>
                {alleSichtbaren.length === 0 ? (
                  !gibtEsUeberhauptHandwerker ? (
                    <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                      Kein Kreditor ist als Handwerker markiert. Handwerker werden unter{' '}
                      <Link to="/kreditoren" className="underline hover:text-amber-900">Rechnungen → Kreditoren</Link>{' '}
                      gepflegt (Kennzeichen „Ist Handwerker" und Gewerke setzen).
                    </p>
                  ) : (
                    <p className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded px-3 py-2">
                      Keine Handwerker für das gewählte Gewerk gefunden.{' '}
                      <button
                        type="button"
                        onClick={() => setGewerkFilter('')}
                        className="text-primary-600 hover:underline"
                      >
                        Gewerk-Filter zurücksetzen
                      </button>
                    </p>
                  )
                ) : (
                  <div className="border border-gray-200 rounded max-h-48 overflow-y-auto">
                    {alleSichtbaren.map(k => (
                      <KreditorZeile
                        key={k.id}
                        kreditor={k}
                        hausfirma={hausIds.has(k.id)}
                        ausgewaehlt={kreditorId === k.id}
                        onSelect={() => setKreditorId(k.id)}
                      />
                    ))}
                  </div>
                )}
                {ausgewaehlterKreditor && !ausgewaehlterKreditor.email && (
                  <p className="text-xs text-red-500 mt-1">
                    Am gewählten Kreditor fehlt die E-Mail-Adresse — für den Auftragsversand zwingend erforderlich.
                  </p>
                )}
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Titel *</label>
                <input
                  className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                  value={titel}
                  onChange={e => setTitel(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Beschreibung</label>
                <textarea
                  className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-20 resize-none"
                  value={beschreibung}
                  onChange={e => setBeschreibung(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-sm font-medium text-gray-700 block mb-1">Gewünscht ab</label>
                  <input
                    type="date"
                    className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                    value={gewuenschtAb}
                    onChange={e => setGewuenschtAb(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700 block mb-1">Priorität</label>
                  <select
                    className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                    value={prioritaet}
                    onChange={e => setPrioritaet(e.target.value as VorgangPrioritaet)}
                  >
                    <option value="niedrig">Niedrig</option>
                    <option value="normal">Normal</option>
                    <option value="hoch">Hoch</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700 block mb-1">Geschätzte Kosten</label>
                  <input
                    type="number"
                    step="0.01"
                    className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                    value={geschaetzteKosten}
                    onChange={e => setGeschaetzteKosten(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex gap-2 pt-1">
                <Button size="sm" disabled={!kannAbsenden || createMutation.isPending} onClick={() => createMutation.mutate()}>
                  {createMutation.isPending ? 'Wird angelegt…' : 'Auftrag anlegen'}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setOffen(false)}>Abbrechen</Button>
              </div>
              {createMutation.isError && (
                <p className="text-red-600 text-sm">{hwaFehlerText(createMutation.error, 'Anlage fehlgeschlagen.')}</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export function VorgangDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)

  const [kommentarText, setKommentarText] = useState('')
  // Default IMMER false (Patrik-Entscheidung): ein Kommentar ist ohne
  // bewusstes Anhaken rein intern — ein Versehen bedeutet dadurch höchstens
  // "Eigentümer sieht etwas nicht", nie das Gegenteil.
  const [kommentarSichtbar, setKommentarSichtbar] = useState(false)
  const [zielStatus, setZielStatus] = useState<VorgangStatus | null>(null)
  const [wiedervorlageDatum, setWiedervorlageDatum] = useState('')
  const [uploadHinweis, setUploadHinweis] = useState<string | null>(null)
  const [vorschlagText, setVorschlagText] = useState('')
  const [verwerfenGrund, setVerwerfenGrund] = useState('')
  const [kopiertHinweis, setKopiertHinweis] = useState(false)
  const [portalVorschauOffen, setPortalVorschauOffen] = useState(false)

  const { data: vorgang, isLoading, error } = useQuery({
    queryKey: ['vorgang', id],
    queryFn: () => vorgaengeApi.get(id!),
    enabled: !!id,
  })

  const { data: mitarbeiter } = useQuery({
    queryKey: ['mitarbeiter-fuer-zuweisung'],
    queryFn: () => mitarbeiterApi.list(),
  })

  const { data: vorgangTypen } = useQuery({
    queryKey: ['vorgang-typen'],
    queryFn: () => vorgaengeApi.typenListe(),
  })

  // Editierbaren Text mit dem aktuellen Vorschlag aus dem Backend abgleichen —
  // löst nur bei tatsächlicher Textänderung vom Server neu aus, damit laufende
  // Eingaben durch Hintergrund-Refetches nicht überschrieben werden.
  useEffect(() => {
    if (vorgang?.antwort_vorschlag) {
      setVorschlagText(vorgang.antwort_vorschlag.text)
    }
  }, [vorgang?.antwort_vorschlag?.id, vorgang?.antwort_vorschlag?.text])

  const statusMutation = useMutation({
    mutationFn: (payload: { status: VorgangStatus; wiedervorlage_am?: string }) =>
      vorgaengeApi.statusWechseln(id!, payload.status, undefined, payload.wiedervorlage_am),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setZielStatus(null)
      setWiedervorlageDatum('')
    },
  })

  const kommentarMutation = useMutation({
    mutationFn: (payload: { text: string; sichtbar: boolean }) =>
      vorgaengeApi.kommentieren(id!, payload.text, payload.sichtbar),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setKommentarText('')
      // Sichtbarkeit NICHT beibehalten — sonst könnte der nächste Kommentar
      // unbemerkt ebenfalls für den Eigentümer sichtbar werden.
      setKommentarSichtbar(false)
    },
  })

  const zuweisenMutation = useMutation({
    mutationFn: (userId: number | null) => vorgaengeApi.zuweisen(id!, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang', id] }),
  })

  const portalSichtbarMutation = useMutation({
    mutationFn: (sichtbar: boolean) => vorgaengeApi.portalSichtbarSetzen(id!, sichtbar),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang', id] }),
  })

  const { data: portalVorschau, isLoading: portalVorschauLaedt } = useQuery({
    queryKey: ['vorgang-portal-vorschau', id],
    queryFn: () => vorgaengeApi.portalVorschau(id!),
    enabled: !!id && portalVorschauOffen,
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => vorgaengeApi.dokumentHochladen(id!, file),
    onSuccess: (ergebnis) => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setUploadHinweis(
        ergebnis.duplikat_warnung
          ? `Achtung: Eine Datei mit identischem Inhalt liegt für diesen Vorgang bereits vor (${ergebnis.dokument.dateiname}).`
          : null,
      )
      if (fileRef.current) fileRef.current.value = ''
    },
  })

  const vorschlagGenerierenMutation = useMutation({
    mutationFn: () => vorgaengeApi.antwortVorschlagGenerieren(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang', id] }),
  })

  const vorschlagBearbeitenMutation = useMutation({
    mutationFn: (text: string) => vorgaengeApi.antwortVorschlagBearbeiten(id!, text),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang', id] }),
  })

  // Freigeben speichert vorher automatisch noch nicht gespeicherte Textänderungen,
  // damit ein Klick auf „Freigeben“ nie ungewollt eine ältere Fassung übernimmt.
  const vorschlagFreigebenMutation = useMutation({
    mutationFn: async () => {
      if (vorgang?.antwort_vorschlag && vorschlagText !== vorgang.antwort_vorschlag.text) {
        await vorgaengeApi.antwortVorschlagBearbeiten(id!, vorschlagText)
      }
      return vorgaengeApi.antwortVorschlagFreigeben(id!)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang', id] }),
  })

  const vorschlagVerwerfenMutation = useMutation({
    mutationFn: (grund?: string) => vorgaengeApi.antwortVorschlagVerwerfen(id!, grund),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setVerwerfenGrund('')
    },
  })

  if (isLoading) return <p className="p-4 text-gray-400">Lade Vorgang…</p>
  if (error || !vorgang) return <p className="p-4 text-red-600">Fehler beim Laden.</p>

  const erlaubteZiele = ERLAUBTE_UEBERGAENGE[vorgang.status] ?? []
  const vorschlagBusy =
    vorschlagGenerierenMutation.isPending ||
    vorschlagBearbeitenMutation.isPending ||
    vorschlagFreigebenMutation.isPending ||
    vorschlagVerwerfenMutation.isPending
  const aktuellerTyp = vorgangTypen?.find(t => t.id === vorgang.typ)
  const geradeErstellt = Date.now() - new Date(vorgang.erstellt_am).getTime() < GERADE_ERSTELLT_SCHWELLE_MS

  function vorschlagKopieren(text: string) {
    navigator.clipboard.writeText(text)
    setKopiertHinweis(true)
    setTimeout(() => setKopiertHinweis(false), 2000)
  }

  function statusKlick(ziel: VorgangStatus) {
    if (ziel === 'wiedervorlage') {
      setZielStatus('wiedervorlage')
      return
    }
    statusMutation.mutate({ status: ziel })
  }

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/vorgaenge" className="text-gray-500 hover:text-gray-800 text-sm">← Zurück</Link>
          <h1 className="text-xl font-semibold font-mono">{vorgang.nummer}</h1>
          <Badge value={vorgang.status} label={STATUS_LABEL[vorgang.status]} />
          <Badge value={vorgang.prioritaet} />
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <h2 className="font-medium text-gray-800">{vorgang.betreff}</h2>
        {vorgang.beschreibung && <p className="text-sm text-gray-600 whitespace-pre-wrap">{vorgang.beschreibung}</p>}
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-gray-500">Typ</dt><dd>{vorgang.typ_bezeichnung}</dd></div>
          <div><dt className="text-gray-500">Quelle</dt><dd>{vorgang.quelle}</dd></div>
          <div><dt className="text-gray-500">Objekt</dt><dd>{vorgang.objekt_bezeichnung ?? '–'}</dd></div>
          <div><dt className="text-gray-500">Einheit</dt><dd>{vorgang.einheit_nr ?? '–'}</dd></div>
          <div><dt className="text-gray-500">Person</dt><dd>{vorgang.person_name ?? '–'}</dd></div>
          <div><dt className="text-gray-500">Fällig am</dt><dd>{vorgang.faellig_am ?? '–'}</dd></div>
          {vorgang.status === 'wiedervorlage' && (
            <div><dt className="text-gray-500">Wiedervorlage am</dt><dd>{vorgang.wiedervorlage_am}</dd></div>
          )}
          <div><dt className="text-gray-500">Erstellt</dt><dd>{DATUM(vorgang.erstellt_am)} von {vorgang.erstellt_von_name ?? '–'}</dd></div>
          {vorgang.geschlossen_am && (
            <div><dt className="text-gray-500">Geschlossen</dt><dd>{DATUM(vorgang.geschlossen_am)} von {vorgang.geschlossen_von_name ?? '–'}</dd></div>
          )}
        </dl>
      </div>

      {/* Antwortvorschlag (KI) */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Antwortvorschlag</h2>

        {!vorgang.antwort_vorschlag && (
          <div className="space-y-3">
            {aktuellerTyp?.antwort_vorschlag_aktiv && geradeErstellt && (
              <p className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded px-3 py-2">
                Für diesen Vorgangstyp wird automatisch ein KI-Antwortvorschlag erzeugt (per Hintergrund-Job).
                Das kann kurz dauern.{' '}
                <button
                  className="text-primary-600 hover:underline"
                  onClick={() => qc.invalidateQueries({ queryKey: ['vorgang', id] })}
                >
                  Aktualisieren
                </button>
              </p>
            )}
            <Button
              size="sm"
              disabled={vorschlagBusy}
              onClick={() => vorschlagGenerierenMutation.mutate()}
            >
              {vorschlagGenerierenMutation.isPending ? 'Wird erzeugt…' : 'Antwortvorschlag erzeugen'}
            </Button>
            {vorschlagGenerierenMutation.isError && (
              <p className="text-red-600 text-sm">
                {fehlerText(vorschlagGenerierenMutation.error, 'Erzeugung fehlgeschlagen.')}
              </p>
            )}
          </div>
        )}

        {vorgang.antwort_vorschlag?.status === 'fehlgeschlagen' && (
          <div className="space-y-3">
            <p className="text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2 text-sm">
              Erzeugung des Antwortvorschlags fehlgeschlagen
              {vorgang.antwort_vorschlag.fehler ? `: ${vorgang.antwort_vorschlag.fehler}` : '.'}
            </p>
            <Button
              size="sm"
              disabled={vorschlagBusy}
              onClick={() => vorschlagGenerierenMutation.mutate()}
            >
              {vorschlagGenerierenMutation.isPending ? 'Wird erzeugt…' : 'Erneut versuchen'}
            </Button>
            {vorschlagGenerierenMutation.isError && (
              <p className="text-red-600 text-sm">
                {fehlerText(vorschlagGenerierenMutation.error, 'Erzeugung fehlgeschlagen.')}
              </p>
            )}
          </div>
        )}

        {vorgang.antwort_vorschlag?.status === 'entwurf' && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                KI-Entwurf — bitte vor Verwendung prüfen
              </span>
              {vorgang.antwort_vorschlag.modell && (
                <span className="text-xs text-gray-400">Modell: {vorgang.antwort_vorschlag.modell}</span>
              )}
            </div>
            <textarea
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-40 resize-y"
              value={vorschlagText}
              disabled={vorschlagBusy}
              onChange={e => setVorschlagText(e.target.value)}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={vorschlagBusy} onClick={() => vorschlagFreigebenMutation.mutate()}>
                Freigeben
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={vorschlagBusy || vorschlagText === vorgang.antwort_vorschlag.text}
                onClick={() => vorschlagBearbeitenMutation.mutate(vorschlagText)}
              >
                Änderungen speichern
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={vorschlagBusy}
                onClick={() => vorschlagGenerierenMutation.mutate()}
              >
                Neu generieren
              </Button>
              <Button size="sm" variant="ghost" onClick={() => vorschlagKopieren(vorschlagText)}>
                {kopiertHinweis ? 'Kopiert!' : 'Kopieren'}
              </Button>
            </div>
            <div className="flex items-center gap-2 pt-1 border-t border-gray-100">
              <input
                type="text"
                placeholder="Grund für Verwerfen (optional)"
                className="rounded border border-gray-300 px-2 py-1 text-xs flex-1"
                value={verwerfenGrund}
                disabled={vorschlagBusy}
                onChange={e => setVerwerfenGrund(e.target.value)}
              />
              <Button
                size="sm"
                variant="danger"
                disabled={vorschlagBusy}
                onClick={() => vorschlagVerwerfenMutation.mutate(verwerfenGrund || undefined)}
              >
                Verwerfen
              </Button>
            </div>
            {(vorschlagFreigebenMutation.isError || vorschlagBearbeitenMutation.isError ||
              vorschlagVerwerfenMutation.isError || vorschlagGenerierenMutation.isError) && (
              <p className="text-red-600 text-sm">
                {fehlerText(
                  vorschlagFreigebenMutation.error ?? vorschlagBearbeitenMutation.error ??
                    vorschlagVerwerfenMutation.error ?? vorschlagGenerierenMutation.error,
                  'Aktion fehlgeschlagen.',
                )}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Zuweisung */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Zuweisung</h2>
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={vorgang.zugewiesen_an ?? ''}
          onChange={e => zuweisenMutation.mutate(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Nicht zugewiesen</option>
          {mitarbeiter?.map(m => (
            <option key={m.id} value={m.user_id}>{m.vollname}</option>
          ))}
        </select>
      </div>

      {/* Statuswechsel */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Status ändern</h2>
        {erlaubteZiele.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Übergänge mehr möglich (endgültiger Status).</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {erlaubteZiele.map(ziel => (
              <Button key={ziel} variant="secondary" size="sm" onClick={() => statusKlick(ziel)}>
                → {STATUS_LABEL[ziel]}
              </Button>
            ))}
          </div>
        )}
        {zielStatus === 'wiedervorlage' && (
          <div className="mt-3 flex items-end gap-2">
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Wiedervorlage am *</label>
              <input
                type="date"
                className="rounded border border-gray-300 px-3 py-2 text-sm"
                value={wiedervorlageDatum}
                onChange={e => setWiedervorlageDatum(e.target.value)}
              />
            </div>
            <Button
              size="sm"
              disabled={!wiedervorlageDatum || statusMutation.isPending}
              onClick={() => statusMutation.mutate({ status: 'wiedervorlage', wiedervorlage_am: wiedervorlageDatum })}
            >
              Bestätigen
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setZielStatus(null)}>Abbrechen</Button>
          </div>
        )}
        {statusMutation.isError && (
          <p className="text-red-600 text-sm mt-2">
            {/* @ts-expect-error axios error shape */}
            {statusMutation.error?.response?.data?.detail ?? 'Statuswechsel fehlgeschlagen.'}
          </p>
        )}
      </div>

      {/* Kommentar */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Kommentar hinzufügen</h2>
        <textarea
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-20 resize-none"
          value={kommentarText}
          onChange={e => setKommentarText(e.target.value)}
        />
        <label className="flex items-center gap-2 mt-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={kommentarSichtbar}
            onChange={e => setKommentarSichtbar(e.target.checked)}
          />
          Für Eigentümer sichtbar
        </label>
        <p className="text-xs text-gray-400 mt-0.5">
          {kommentarSichtbar
            ? 'Dieser Kommentar wird für den Eigentümer sichtbar (sobald es ein Eigentümer-Portal gibt).'
            : 'Nicht angehakt = rein intern. Der Eigentümer bekommt diesen Kommentar NIE zu sehen.'}
        </p>
        <div className="mt-2">
          <Button
            size="sm"
            disabled={!kommentarText.trim() || kommentarMutation.isPending}
            onClick={() => kommentarMutation.mutate({ text: kommentarText, sichtbar: kommentarSichtbar })}
          >
            Kommentar speichern
          </Button>
        </div>
      </div>

      {/* Eigentümer-Portal: Sichtbarkeit + Vorschau */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Eigentümer-Portal</h2>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={vorgang.portal_sichtbar}
            disabled={portalSichtbarMutation.isPending}
            onChange={e => portalSichtbarMutation.mutate(e.target.checked)}
          />
          Vorgang für den Eigentümer sichtbar
        </label>
        <p className="text-xs text-gray-400 mt-1">
          Solange dieser Schalter aus ist, sieht der Eigentümer diesen Vorgang überhaupt nicht — unabhängig davon,
          welche Einträge als „für Eigentümer sichtbar" markiert sind. Es gibt aktuell noch kein Eigentümer-Portal;
          dieser Schalter bereitet es vor.
        </p>
        <div className="mt-3 pt-3 border-t border-gray-100">
          <Button size="sm" variant="secondary" onClick={() => setPortalVorschauOffen(o => !o)}>
            {portalVorschauOffen ? 'Portal-Vorschau schließen' : 'Portal-Vorschau anzeigen — was sieht der Eigentümer?'}
          </Button>
          {portalVorschauOffen && (
            <div className="mt-3 bg-gray-50 border border-gray-200 rounded p-3">
              {portalVorschauLaedt && <p className="text-sm text-gray-400">Lade Vorschau…</p>}
              {portalVorschau && !portalVorschau.sichtbar && (
                <p className="text-sm text-amber-700">
                  Nicht freigegeben — der Eigentümer sieht diesen Vorgang aktuell nicht (Schalter oben ist aus).
                </p>
              )}
              {portalVorschau?.sichtbar && (
                <div className="space-y-2 text-sm">
                  <p className="font-medium text-gray-700">{portalVorschau.nummer} — {portalVorschau.betreff}</p>
                  {portalVorschau.beschreibung && (
                    <p className="text-gray-600 whitespace-pre-wrap">{portalVorschau.beschreibung}</p>
                  )}
                  <p className="text-gray-500 text-xs">
                    Status: {portalVorschau.status_anzeige}
                    {portalVorschau.objekt_bezeichnung && ` · Objekt: ${portalVorschau.objekt_bezeichnung}`}
                    {portalVorschau.einheit_nr && ` · Einheit: ${portalVorschau.einheit_nr}`}
                  </p>
                  <ul className="space-y-2 pt-2 border-t border-gray-200">
                    {portalVorschau.ereignisse.map((e, idx) => (
                      <li key={idx} className="border-l-2 border-gray-300 pl-2">
                        <div className="text-xs text-gray-400">{e.typ_anzeige} — {DATUM(e.erstellt_am)}</div>
                        {e.text && <div className="text-gray-700">{e.text}</div>}
                      </li>
                    ))}
                    {portalVorschau.ereignisse.length === 0 && (
                      <li className="text-gray-400 text-xs">Noch keine für den Eigentümer sichtbaren Einträge.</li>
                    )}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Dokumente */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Dokumente</h2>
        <ul className="divide-y divide-gray-100 mb-3">
          {vorgang.dokumente.map(d => (
            <li key={d.id} className="py-2 text-sm flex justify-between">
              <span>{d.dateiname} {d.version > 1 && <span className="text-gray-400">(v{d.version})</span>}</span>
              <span className="text-gray-400">{DATUM(d.hochgeladen_am)}</span>
            </li>
          ))}
          {vorgang.dokumente.length === 0 && (
            <li className="py-2 text-sm text-gray-400">Keine Dokumente vorhanden.</li>
          )}
        </ul>
        <input
          ref={fileRef}
          type="file"
          className="text-sm"
          onChange={e => {
            const file = e.target.files?.[0]
            if (file) uploadMutation.mutate(file)
          }}
        />
        {uploadHinweis && (
          <p className="text-yellow-700 bg-yellow-50 border border-yellow-200 rounded px-3 py-2 text-sm mt-2">
            {uploadHinweis}
          </p>
        )}
        {uploadMutation.isError && (
          <p className="text-red-600 text-sm mt-2">
            {/* @ts-expect-error axios error shape */}
            {uploadMutation.error?.response?.data?.detail ?? 'Upload fehlgeschlagen.'}
          </p>
        )}
      </div>

      {/* Handwerkeraufträge */}
      <HandwerkerBeauftragenSection vorgang={vorgang} />

      {/* Verlauf */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Verlauf</h2>
        <ul className="space-y-3">
          {vorgang.ereignisse.map(e => (
            <li key={e.id} className="text-sm border-l-2 border-gray-200 pl-3">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-700">{EREIGNIS_LABEL[e.typ] ?? e.typ}</span>
                {e.intern ? (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-500">
                    Intern
                  </span>
                ) : (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
                    Für Eigentümer sichtbar
                  </span>
                )}
                <span className="text-gray-400 text-xs">{DATUM(e.erstellt_am)}</span>
                {e.erstellt_von_name && <span className="text-gray-400 text-xs">— {e.erstellt_von_name}</span>}
              </div>
              {e.typ === 'antwort_vorschlag_freigegeben' && e.text ? (
                <div className="mt-1 bg-green-50 border border-green-200 rounded p-3">
                  <p className="text-gray-700 whitespace-pre-wrap">{e.text}</p>
                  <button
                    className="mt-2 text-xs text-primary-600 hover:underline"
                    onClick={() => navigator.clipboard.writeText(e.text ?? '')}
                  >
                    Text kopieren
                  </button>
                </div>
              ) : (
                e.text && <p className="text-gray-600 mt-0.5">{e.text}</p>
              )}
              {(e.alter_wert || e.neuer_wert) && (
                <p className="text-gray-400 text-xs mt-0.5">{e.alter_wert ?? '–'} → {e.neuer_wert ?? '–'}</p>
              )}
            </li>
          ))}
          {vorgang.ereignisse.length === 0 && (
            <li className="text-sm text-gray-400">Noch keine Ereignisse.</li>
          )}
        </ul>
      </div>
    </div>
  )
}
