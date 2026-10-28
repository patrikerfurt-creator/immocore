import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { vorgaengeApi } from '../../api/vorgaenge'
import { mitarbeiterApi } from '../../api/mitarbeiter'
import { handwerkerApi } from '../../api/handwerker'
import { objekteApi } from '../../api/objekte'
import { dokumenteApi } from '../../api/dokumente'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type {
  HandwerkerauftragCreatePayload, HandwerkerauftragDetail, Kreditor, VorgangDetail as VorgangDetailTyp,
  VorgangEreignis, VorgangPrioritaet, VorgangStatus, VorgangZeiteintragCreatePayload,
} from '../../types'
import { HWA_STATUS_LABEL, fehlerText as hwaFehlerText } from '../handwerker/shared'
import { SchreibenErstellenButton } from '../korrespondenz/schreiben/SchreibenErstellenDialog'

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
  mail_eingegangen: 'E-Mail eingegangen',
  schreiben_erstellt: 'Schreiben erstellt',
  schreiben_versendet: 'Schreiben versendet',
  antwort_freigegeben: 'Antwort fürs Portal freigegeben',
  mail_antwort_gesendet: 'Mail-Antwort an Kunde gesendet',
  portal_antwort: 'Antwort über Portal (Kunde)',
}

// Welche Ereignisse sind Teil der Konversation (Chat) — und auf welcher Seite?
// „eingehend" = vom Kunden (links), „ausgehend" = von uns (rechts). Alles
// andere ist interne Aktivität und landet im einklappbaren Aktivitätsbereich.
const CHAT_EINGEHEND = new Set(['mail_eingegangen', 'portal_antwort'])
const CHAT_AUSGEHEND = new Set([
  'antwort_freigegeben', 'antwort_vorschlag_freigegeben',
  'mail_antwort_gesendet', 'schreiben_versendet',
])

// Beschriftung der Chat-Sprechblasen je Ereignistyp.
const CHAT_LABEL: Record<string, string> = {
  mail_eingegangen: 'E-Mail vom Kunden',
  portal_antwort: 'Antwort über Portal (Kunde)',
  antwort_freigegeben: 'Antwort — fürs Portal freigegeben',
  antwort_vorschlag_freigegeben: 'Antwort — fürs Portal freigegeben',
  mail_antwort_gesendet: 'Mail-Antwort an den Kunden',
  schreiben_versendet: 'Schreiben versendet',
  kommentar: 'Für den Eigentümer sichtbarer Hinweis',
}

// Gehört ein Ereignis in den Chat-Verlauf? (Konversation vs. interne Aktivität)
// Ein ``kommentar`` zählt nur dann zur Konversation, wenn er bewusst
// eigentümer-sichtbar (``intern=false``) gespeichert wurde.
function istKonversation(e: VorgangEreignis): boolean {
  return CHAT_EINGEHEND.has(e.typ) || CHAT_AUSGEHEND.has(e.typ) || (e.typ === 'kommentar' && !e.intern)
}

// Eine Sprechblase im Chat. ``ausgehend`` = von uns (rechts), sonst vom Kunden
// (links). ``originalMailDokId`` blendet bei eingegangenen Mails den Link zur
// Original-.eml im DMS ein.
function ChatBubble({
  ausgehend, label, datum, autor, originalMailDokId, children,
}: {
  ausgehend: boolean
  label: string
  datum: string
  autor?: string | null
  originalMailDokId?: string | null
  children: ReactNode
}) {
  return (
    <div className={`flex ${ausgehend ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg border px-3 py-2 ${
          ausgehend ? 'bg-primary-50 border-primary-100' : 'bg-gray-50 border-gray-200'
        }`}
      >
        <div className="flex items-center gap-2 flex-wrap text-xs text-gray-400 mb-1">
          <span className="font-medium text-gray-600">{label}</span>
          <span>{datum}</span>
          {autor && <span>· {autor}</span>}
        </div>
        <div className="text-sm text-gray-700">{children}</div>
        {originalMailDokId && (
          <button
            type="button"
            onClick={() => dokumenteApi.openMailVorschau(originalMailDokId)}
            className="mt-1 text-xs text-primary-600 hover:underline"
          >
            Original-Mail öffnen
          </button>
        )}
      </div>
    </div>
  )
}

function DATUM(s: string | null) {
  return s ? new Date(s).toLocaleString('de-DE') : '–'
}

// Dauer-Hilfen für die Zeiterfassung: intern wird in Minuten gerechnet,
// angezeigt/eingegeben als "h:mm".
function minutenZuHHMM(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${h}:${String(m).padStart(2, '0')}`
}

// Parst "h:mm" ODER eine reine Minutenzahl. null = ungültige Eingabe.
function parseDauerZuMinuten(text: string): number | null {
  const t = text.trim()
  if (!t) return 0
  if (t.includes(':')) {
    const [h, m] = t.split(':')
    const hh = Number(h)
    const mm = Number(m)
    if (!Number.isFinite(hh) || !Number.isFinite(mm) || hh < 0 || mm < 0 || mm > 59) return null
    return hh * 60 + mm
  }
  const n = Number(t)
  if (!Number.isFinite(n) || n < 0) return null
  return Math.round(n)
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

// Optionale Zeiterfassung (Sonderkosten) — nur relevant, wenn der Vorgang als
// „separat abrechenbar" markiert ist. Erfasst Dauer (Stoppuhr oder von Hand)
// und gefahrene Kilometer; die Rechnungsstellung selbst erfolgt extern, hier
// gibt es nur die Nachweis-Tabelle + CSV-Export.
function ZeiterfassungSection({
  vorgang, mitarbeiter,
}: {
  vorgang: VorgangDetailTyp
  mitarbeiter?: { user_id: number; vollname: string }[]
}) {
  const qc = useQueryClient()
  const id = vorgang.id
  const timerKey = `vorgang-timer-${id}`

  // Stoppuhr: Startzeitpunkt (ms) überlebt via localStorage einen Reload.
  const [laufSeit, setLaufSeit] = useState<number | null>(() => {
    try {
      const s = localStorage.getItem(timerKey)
      return s ? Number(s) : null
    } catch {
      return null
    }
  })
  const [jetzt, setJetzt] = useState(Date.now())

  const [mitarbeiterId, setMitarbeiterId] = useState<number | ''>(vorgang.zugewiesen_an ?? '')
  const [datum, setDatum] = useState(() => new Date().toISOString().slice(0, 10))
  const [taetigkeit, setTaetigkeit] = useState('')
  const [dauerText, setDauerText] = useState('')
  const [kilometer, setKilometer] = useState('')

  useEffect(() => {
    if (laufSeit == null) return
    const iv = setInterval(() => setJetzt(Date.now()), 1000)
    return () => clearInterval(iv)
  }, [laufSeit])

  const abrechenbarMutation = useMutation({
    mutationFn: (an: boolean) => vorgaengeApi.abrechenbarSetzen(id, an),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang', id] }),
  })
  const addMutation = useMutation({
    mutationFn: (payload: VorgangZeiteintragCreatePayload) => vorgaengeApi.zeiteintragHinzufuegen(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setTaetigkeit('')
      setDauerText('')
      setKilometer('')
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (eintragId: string) => vorgaengeApi.zeiteintragLoeschen(id, eintragId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang', id] }),
  })

  function startStoppuhr() {
    const t = Date.now()
    setLaufSeit(t)
    setJetzt(t)
    try { localStorage.setItem(timerKey, String(t)) } catch { /* ignore */ }
  }
  function stopStoppuhr() {
    if (laufSeit == null) return
    const min = Math.max(1, Math.round((Date.now() - laufSeit) / 60000))
    const vorhanden = parseDauerZuMinuten(dauerText) || 0
    setDauerText(minutenZuHHMM(vorhanden + min))
    setLaufSeit(null)
    try { localStorage.removeItem(timerKey) } catch { /* ignore */ }
  }

  const minuten = parseDauerZuMinuten(dauerText)
  const kmNum = kilometer.trim() ? Number(kilometer.replace(',', '.')) : 0
  const kmGueltig = Number.isFinite(kmNum) && kmNum >= 0
  const kannSpeichern =
    mitarbeiterId !== '' && !!taetigkeit.trim() && minuten !== null && kmGueltig &&
    ((minuten ?? 0) > 0 || kmNum > 0) && !addMutation.isPending

  function speichern() {
    if (!kannSpeichern) return
    addMutation.mutate({
      mitarbeiter: Number(mitarbeiterId),
      datum,
      taetigkeit: taetigkeit.trim(),
      dauer_minuten: minuten ?? 0,
      kilometer: String(kmNum),
    })
  }

  const laufMMSS = laufSeit != null
    ? (() => {
        const sek = Math.max(0, Math.floor((jetzt - laufSeit) / 1000))
        return `${Math.floor(sek / 60)}:${String(sek % 60).padStart(2, '0')}`
      })()
    : null

  // Schalter aus → schlanke Karte mit nur dem Haken.
  if (!vorgang.abrechenbar) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-2">Zeiterfassung (Sonderkosten)</h2>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={false}
            disabled={abrechenbarMutation.isPending}
            onChange={() => abrechenbarMutation.mutate(true)}
          />
          Dieser Vorgang ist <strong>separat abrechenbar</strong> — Zeiten &amp; Kilometer erfassen
        </label>
        <p className="text-xs text-gray-400 mt-1">
          Nur einschalten, wenn der Vorgang als Sonderleistung berechnet werden kann. Danach lassen sich
          Tätigkeiten mit Dauer (Stoppuhr oder von Hand) und gefahrene Kilometer erfassen.
        </p>
      </div>
    )
  }

  const eintraege = vorgang.zeiteintraege ?? []
  const summe = vorgang.zeit_summe

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h2 className="font-medium text-gray-800">Zeiterfassung (Sonderkosten)</h2>
        <div className="flex items-center gap-3">
          {eintraege.length > 0 && (
            <Button size="sm" variant="secondary" onClick={() => vorgaengeApi.zeitenExportieren(id, vorgang.nummer)}>
              CSV-Export
            </Button>
          )}
          <label className="flex items-center gap-2 text-xs text-gray-500">
            <input
              type="checkbox"
              checked
              disabled={abrechenbarMutation.isPending}
              onChange={() => abrechenbarMutation.mutate(false)}
            />
            separat abrechenbar
          </label>
        </div>
      </div>

      {/* Tabelle der Einträge */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-200">
              <th className="py-2 pr-3 font-medium">Datum</th>
              <th className="py-2 pr-3 font-medium">Mitarbeiter</th>
              <th className="py-2 pr-3 font-medium">Tätigkeit</th>
              <th className="py-2 pr-3 font-medium text-right">Dauer</th>
              <th className="py-2 pr-3 font-medium text-right">km</th>
              <th className="py-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {eintraege.map(e => (
              <tr key={e.id} className="border-b border-gray-100">
                <td className="py-2 pr-3 whitespace-nowrap">{new Date(e.datum).toLocaleDateString('de-DE')}</td>
                <td className="py-2 pr-3">{e.mitarbeiter_name ?? '–'}</td>
                <td className="py-2 pr-3">{e.taetigkeit}</td>
                <td className="py-2 pr-3 text-right whitespace-nowrap">{minutenZuHHMM(e.dauer_minuten)}</td>
                <td className="py-2 pr-3 text-right whitespace-nowrap">
                  {Number(e.kilometer) > 0 ? Number(e.kilometer).toLocaleString('de-DE', { minimumFractionDigits: 1 }) : '–'}
                </td>
                <td className="py-2 text-right">
                  <button
                    type="button"
                    className="text-gray-400 hover:text-red-600"
                    title="Eintrag löschen"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(e.id)}
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
            {eintraege.length === 0 && (
              <tr>
                <td colSpan={6} className="py-3 text-center text-gray-400">Noch keine Zeiten erfasst.</td>
              </tr>
            )}
          </tbody>
          {eintraege.length > 0 && summe && (
            <tfoot>
              <tr className="border-t border-gray-200 font-medium text-gray-700">
                <td className="py-2 pr-3" colSpan={3}>Summe ({summe.anzahl})</td>
                <td className="py-2 pr-3 text-right whitespace-nowrap">{minutenZuHHMM(summe.minuten)}</td>
                <td className="py-2 pr-3 text-right whitespace-nowrap">
                  {Number(summe.kilometer).toLocaleString('de-DE', { minimumFractionDigits: 1 })}
                </td>
                <td></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* Erfassungszeile */}
      <div className="mt-4 border-t border-gray-100 pt-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Mitarbeiter *</label>
            <select
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={mitarbeiterId}
              onChange={e => setMitarbeiterId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Mitarbeiter wählen…</option>
              {mitarbeiter?.map(m => (
                <option key={m.user_id} value={m.user_id}>{m.vollname}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Datum *</label>
            <input
              type="date"
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={datum}
              onChange={e => setDatum(e.target.value)}
            />
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">Tätigkeit *</label>
          <input
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            placeholder="z.B. Telefonat mit Architekt"
            value={taetigkeit}
            onChange={e => setTaetigkeit(e.target.value)}
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Dauer (h:mm oder Minuten)</label>
            <div className="flex items-center gap-2">
              <input
                className={`w-full rounded border px-3 py-2 text-sm ${minuten === null ? 'border-red-400' : 'border-gray-300'}`}
                placeholder="0:30"
                value={dauerText}
                onChange={e => setDauerText(e.target.value)}
              />
              {laufSeit == null ? (
                <Button size="sm" variant="secondary" onClick={startStoppuhr} title="Stoppuhr starten">▶ Start</Button>
              ) : (
                <Button size="sm" variant="danger" onClick={stopStoppuhr} title="Stoppuhr stoppen">■ {laufMMSS}</Button>
              )}
            </div>
            {minuten === null && <p className="text-xs text-red-500 mt-1">Ungültige Dauer (z.B. „1:30" oder „90").</p>}
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Gefahrene Kilometer</label>
            <input
              className={`w-full rounded border px-3 py-2 text-sm ${!kmGueltig ? 'border-red-400' : 'border-gray-300'}`}
              placeholder="0"
              value={kilometer}
              onChange={e => setKilometer(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button size="sm" disabled={!kannSpeichern} onClick={speichern}>
            {addMutation.isPending ? 'Wird gespeichert…' : 'Eintrag hinzufügen'}
          </Button>
          {laufSeit != null && (
            <span className="text-xs text-amber-600">Stoppuhr läuft — beim Stoppen wird die Zeit übernommen.</span>
          )}
        </div>
        {addMutation.isError && (
          <p className="text-red-600 text-sm">{fehlerText(addMutation.error, 'Speichern fehlgeschlagen.')}</p>
        )}
      </div>
    </div>
  )
}

// Einklappbarer Nebenbereich (für selten genutzte Abschnitte wie das
// Eigentümer-Portal), damit die Seitenleiste nicht unnötig lang wird.
function Klappbox({
  titel, standardOffen = false, children,
}: { titel: string; standardOffen?: boolean; children: ReactNode }) {
  const [offen, setOffen] = useState(standardOffen)
  return (
    <div className="bg-white rounded-lg border border-gray-200">
      <button
        type="button"
        onClick={() => setOffen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-left"
      >
        <span className="font-medium text-gray-800">{titel}</span>
        <span className="text-gray-400 text-xs">{offen ? '▲ einklappen' : '▼ anzeigen'}</span>
      </button>
      {offen && <div className="px-5 pb-5 pt-0">{children}</div>}
    </div>
  )
}

// Trennt bei importierten Mails den neu geschriebenen Teil von der zitierten
// Vorkorrespondenz. Jede Antwortmail zitiert die komplette bisherige Konversation;
// ohne Trennung steht dieselbe Ursprungsnachricht im Verlauf mehrfach voll
// ausgeschrieben. zitat ist null, wenn keine zitierte Historie erkannt wurde.
function zitatTrennen(text: string): { neu: string; zitat: string | null } {
  // Gängige Zitat-/Weiterleitungs-Marker verschiedener Mailprogramme.
  const marker: RegExp[] = [
    /-{2,}\s*Ursprüngliche Nachricht\s*-{2,}/i,
    /-{2,}\s*Original Message\s*-{2,}/i,
    /-{2,}\s*Weitergeleitete Nachricht\s*-{2,}/i,
    /-{2,}\s*Forwarded message\s*-{2,}/i,
    // "Am 16.10.26 um 10:17 schrieb …" (GMX/Apple/Thunderbird), mit oder ohne Doppelpunkt.
    /\n\s*Am .{1,160}? schrieb\b/i,
    /\n\s*On .{1,160}? wrote\b/i,
    // Klassisch zitierte Zeilen mit vorangestelltem ">".
    /\n>/,
  ]
  let idx = -1
  for (const re of marker) {
    const m = text.match(re)
    if (m && m.index != null && (idx === -1 || m.index < idx)) idx = m.index
  }
  // Kein Marker oder Marker ganz am Anfang (nichts Neues davor) → nicht trennen.
  if (idx <= 0) return { neu: text, zitat: null }
  const neu = text.slice(0, idx).trimEnd()
  const zitat = text.slice(idx).trim()
  if (!neu) return { neu: text, zitat: null }
  return { neu, zitat }
}

// Ereignistext im Verlauf: neuer Mail-Text direkt, zitierte Historie erst auf
// Klick. whitespace-pre-wrap erhält außerdem die Zeilenumbrüche der Mail.
function EreignisText({ text }: { text: string }) {
  const [offen, setOffen] = useState(false)
  const { neu, zitat } = zitatTrennen(text)
  return (
    <div className="text-gray-600 mt-0.5">
      <p className="whitespace-pre-wrap">{neu}</p>
      {zitat && (
        <div className="mt-1">
          <button
            type="button"
            onClick={() => setOffen(o => !o)}
            className="text-xs text-primary-600 hover:underline"
          >
            {offen ? '▲ Zitierte Mail-Historie ausblenden' : '▼ Zitierte Mail-Historie anzeigen'}
          </button>
          {offen && (
            <div className="mt-1 border-l-2 border-gray-200 pl-3 text-xs text-gray-400 whitespace-pre-wrap">
              {zitat}
            </div>
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

  // Ein gemeinsames Eingabefeld für die Antwort am Ende des Chats — der
  // „Antwortvorschlag erzeugen"-Button füllt es, die Buttons „Freigeben" /
  // „Per Mail senden" / „Interner Vermerk" verschicken seinen Inhalt.
  const [composerText, setComposerText] = useState('')
  const [zielStatus, setZielStatus] = useState<VorgangStatus | null>(null)
  const [wiedervorlageDatum, setWiedervorlageDatum] = useState('')
  const [uploadHinweis, setUploadHinweis] = useState<string | null>(null)
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

  const statusMutation = useMutation({
    mutationFn: (payload: { status: VorgangStatus; wiedervorlage_am?: string }) =>
      vorgaengeApi.statusWechseln(id!, payload.status, undefined, payload.wiedervorlage_am),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setZielStatus(null)
      setWiedervorlageDatum('')
    },
  })

  // Interner Vermerk: immer rein intern (sichtbar=false) — der Eigentümer
  // bekommt ihn NIE zu sehen. Die eigentümer-sichtbare Kommunikation läuft
  // über „Freigeben" / „Per Mail senden".
  const kommentarMutation = useMutation({
    mutationFn: (text: string) => vorgaengeApi.kommentieren(id!, text, false),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setComposerText('')
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

  // „Antwortvorschlag erzeugen" füllt nur das Eingabefeld — der Mitarbeiter
  // entscheidet danach, ob und wie (Portal/Mail) er antwortet.
  const vorschlagGenerierenMutation = useMutation({
    mutationFn: () => vorgaengeApi.antwortVorschlagGenerieren(id!),
    onSuccess: (vorschlag) => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      if (vorschlag?.text) setComposerText(vorschlag.text)
    },
  })

  // Antwort an den Kunden: Freigabe fürs Portal oder direkte Mail.
  const antwortMutation = useMutation({
    mutationFn: (payload: { text: string; kanal: 'mail' | 'portal' }) =>
      vorgaengeApi.antwortSenden(id!, payload.text, payload.kanal),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang', id] })
      setComposerText('')
    },
  })

  if (isLoading) return <p className="p-4 text-gray-400">Lade Vorgang…</p>
  if (error || !vorgang) return <p className="p-4 text-red-600">Fehler beim Laden.</p>

  const erlaubteZiele = ERLAUBTE_UEBERGAENGE[vorgang.status] ?? []
  const antwortBusy = antwortMutation.isPending || vorschlagGenerierenMutation.isPending || kommentarMutation.isPending

  // Chat = Konversation (Sprechblasen) getrennt von interner Aktivität.
  const konversation = vorgang.ereignisse.filter(istKonversation)
  const internEreignisse = vorgang.ereignisse.filter(e => !istKonversation(e))
  // Die Original-.eml der ersten Mail (für den Link an der ersten Sprechblase).
  const ersteMailDok = [...vorgang.dokumente]
    .filter(d => /\.(eml|msg)$/i.test(d.dateiname))
    .sort((a, b) => a.hochgeladen_am.localeCompare(b.hochgeladen_am))[0]

  function statusKlick(ziel: VorgangStatus) {
    if (ziel === 'wiedervorlage') {
      setZielStatus('wiedervorlage')
      return
    }
    statusMutation.mutate({ status: ziel })
  }

  // Wiedervorlage überfällig? (nur relevant im Status 'wiedervorlage')
  const wiedervorlageUeberfaellig =
    vorgang.status === 'wiedervorlage' && !!vorgang.wiedervorlage_am &&
    new Date(vorgang.wiedervorlage_am) < new Date(new Date().toDateString())

  return (
    <div className="p-4 max-w-6xl mx-auto space-y-5">
      {/* Sticky-Kopf: Nummer, Status, Priorität und Hauptaktion bleiben beim
          Scrollen sichtbar. */}
      <div className="sticky top-4 z-10 bg-white rounded-lg border border-gray-200 shadow-sm px-5 py-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <Link to="/vorgaenge" className="text-gray-500 hover:text-gray-800 text-sm">← Zurück</Link>
          <h1 className="text-xl font-semibold font-mono">{vorgang.nummer}</h1>
          <Badge value={vorgang.status} label={STATUS_LABEL[vorgang.status]} />
          <Badge value={vorgang.prioritaet} />
        </div>
        <SchreibenErstellenButton
          anlass="vorgang_antwort"
          vorgangId={vorgang.id}
          person={vorgang.person ? { id: vorgang.person, name: vorgang.person_name ?? 'Person' } : null}
          einheitId={vorgang.einheit}
          objektId={vorgang.objekt}
          onErstellt={() => qc.invalidateQueries({ queryKey: ['vorgang', id] })}
        />
      </div>

      {/* Kontextzeile: das Wichtigste auf einen Blick, ohne Scrollen. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm px-1">
        <span><span className="text-gray-400">Typ:</span> <span className="text-gray-700">{vorgang.typ_bezeichnung}</span></span>
        {vorgang.objekt_bezeichnung && (
          <span><span className="text-gray-400">Objekt:</span> <span className="text-gray-700">{vorgang.objekt_bezeichnung}</span></span>
        )}
        {vorgang.einheit_nr && (
          <span><span className="text-gray-400">Einheit:</span> <span className="text-gray-700">{vorgang.einheit_nr}</span></span>
        )}
        {vorgang.person_name && (
          <span><span className="text-gray-400">Person:</span> <span className="text-gray-700">{vorgang.person_name}</span></span>
        )}
        {vorgang.status === 'wiedervorlage' && vorgang.wiedervorlage_am && (
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
            wiedervorlageUeberfaellig ? 'bg-red-100 text-red-700' : 'bg-purple-100 text-purple-700'
          }`}>
            Wiedervorlage {new Date(vorgang.wiedervorlage_am).toLocaleDateString('de-DE')}
            {wiedervorlageUeberfaellig && ' — überfällig'}
          </span>
        )}
      </div>

      {/* Zwei Spalten: links Inhalt, rechts Steuerung & Nebeninfos. */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-start">
        {/* ── Hauptspalte ── */}
        <div className="lg:col-span-2 space-y-5">

      {/* Chat-Verlauf: Konversation als Sprechblasen, Antwort-Eingabe unten */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-1">{vorgang.betreff}</h2>
        <p className="text-xs text-gray-400 mb-4">Konversation mit dem Kunden</p>

        <div className="space-y-3">
          {/* Erste Nachricht: die Beschreibung/ursprüngliche Mail */}
          <ChatBubble
            ausgehend={false}
            label="Ursprüngliche Nachricht"
            datum={DATUM(vorgang.erstellt_am)}
            autor={vorgang.person_name}
            originalMailDokId={ersteMailDok?.id}
          >
            {vorgang.beschreibung
              ? <EreignisText text={vorgang.beschreibung} />
              : <span className="text-gray-400">Keine Beschreibung.</span>}
          </ChatBubble>

          {konversation.map(e => {
            const ausgehend = CHAT_AUSGEHEND.has(e.typ) || e.typ === 'kommentar'
            const istEingehendeMail = e.typ === 'mail_eingegangen'
            return (
              <ChatBubble
                key={e.id}
                ausgehend={ausgehend}
                label={CHAT_LABEL[e.typ] ?? (EREIGNIS_LABEL[e.typ] ?? e.typ)}
                datum={DATUM(e.erstellt_am)}
                autor={e.erstellt_von_name}
                originalMailDokId={istEingehendeMail ? e.dokument : null}
              >
                {istEingehendeMail
                  ? (e.text && <EreignisText text={e.text} />)
                  : <p className="whitespace-pre-wrap">{e.text}</p>}
              </ChatBubble>
            )
          })}
        </div>

        {/* Composer: beantwortet immer die letzte Nachricht */}
        <div className="border-t border-gray-100 pt-4 mt-4">
          <textarea
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-28 resize-y"
            placeholder="Antwort an den Kunden schreiben – oder einen Antwortvorschlag erzeugen lassen…"
            value={composerText}
            disabled={antwortBusy}
            onChange={e => setComposerText(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={antwortBusy}
              onClick={() => vorschlagGenerierenMutation.mutate()}
            >
              {vorschlagGenerierenMutation.isPending ? 'Erzeuge…' : '✨ Antwortvorschlag erzeugen'}
            </Button>
            <div className="flex-1" />
            <Button
              size="sm"
              variant="ghost"
              disabled={!composerText.trim() || antwortBusy}
              onClick={() => kommentarMutation.mutate(composerText)}
            >
              Interner Vermerk
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!composerText.trim() || antwortBusy}
              onClick={() => antwortMutation.mutate({ text: composerText, kanal: 'mail' })}
            >
              Per Mail senden
            </Button>
            <Button
              size="sm"
              disabled={!composerText.trim() || antwortBusy}
              onClick={() => antwortMutation.mutate({ text: composerText, kanal: 'portal' })}
            >
              Fürs Portal freigeben
            </Button>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            „Fürs Portal freigeben" zeigt die Antwort dem Eigentümer im Portal. „Per Mail senden"
            schickt sie direkt per E-Mail (für Kunden ohne Portal-Zugang). „Interner Vermerk" bleibt rein intern.
          </p>
          {(antwortMutation.isError || vorschlagGenerierenMutation.isError || kommentarMutation.isError) && (
            <p className="text-red-600 text-sm mt-1">
              {fehlerText(
                antwortMutation.error ?? vorschlagGenerierenMutation.error ?? kommentarMutation.error,
                'Aktion fehlgeschlagen.',
              )}
            </p>
          )}
        </div>
      </div>

      {/* Handwerkeraufträge (Hauptspalte: das Anlage-Formular braucht Breite) */}
      <HandwerkerBeauftragenSection vorgang={vorgang} />

      {/* Zeiterfassung (optionale Sonderkosten) */}
      <ZeiterfassungSection vorgang={vorgang} mitarbeiter={mitarbeiter} />

      {/* Aktivität (intern): Status, Zuweisung, Dokumente, KI-Entwürfe usw. —
          bewusst getrennt vom Chat, standardmäßig eingeklappt. */}
      <Klappbox titel="Aktivität (intern)">
        <ul className="space-y-3">
          {internEreignisse.map(e => (
            <li key={e.id} className="text-sm border-l-2 border-gray-200 pl-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-700">{EREIGNIS_LABEL[e.typ] ?? e.typ}</span>
                <span className="text-gray-400 text-xs">{DATUM(e.erstellt_am)}</span>
                {e.erstellt_von_name && <span className="text-gray-400 text-xs">— {e.erstellt_von_name}</span>}
              </div>
              {e.text && <EreignisText text={e.text} />}
              {(e.alter_wert || e.neuer_wert) && (
                <p className="text-gray-400 text-xs mt-0.5">{e.alter_wert ?? '–'} → {e.neuer_wert ?? '–'}</p>
              )}
            </li>
          ))}
          {internEreignisse.length === 0 && (
            <li className="text-sm text-gray-400">Keine internen Ereignisse.</li>
          )}
        </ul>
      </Klappbox>
        </div>

        {/* ── Seitenleiste: Steuerung & Nebeninfos ── */}
        <div className="lg:col-span-1 space-y-5">

          {/* Bearbeitung: Zuweisung + Status gebündelt */}
          <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
            <div>
              <h2 className="font-medium text-gray-800 mb-2">Zuweisung</h2>
              <select
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={vorgang.zugewiesen_an ?? ''}
                onChange={e => zuweisenMutation.mutate(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Nicht zugewiesen</option>
                {mitarbeiter?.map(m => (
                  <option key={m.id} value={m.user_id}>{m.vollname}</option>
                ))}
              </select>
            </div>

            <div className="border-t border-gray-100 pt-4">
              <h2 className="font-medium text-gray-800 mb-2">Status ändern</h2>
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
                <div className="mt-3 space-y-2">
                  <label className="text-sm font-medium text-gray-700 block">Wiedervorlage am *</label>
                  <input
                    type="date"
                    className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                    value={wiedervorlageDatum}
                    onChange={e => setWiedervorlageDatum(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={!wiedervorlageDatum || statusMutation.isPending}
                      onClick={() => statusMutation.mutate({ status: 'wiedervorlage', wiedervorlage_am: wiedervorlageDatum })}
                    >
                      Bestätigen
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setZielStatus(null)}>Abbrechen</Button>
                  </div>
                </div>
              )}
              {statusMutation.isError && (
                <p className="text-red-600 text-sm mt-2">
                  {/* @ts-expect-error axios error shape */}
                  {statusMutation.error?.response?.data?.detail ?? 'Statuswechsel fehlgeschlagen.'}
                </p>
              )}
            </div>
          </div>

          {/* Details */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <h2 className="font-medium text-gray-800 mb-3">Details</h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500">Quelle</dt>
                <dd className="text-gray-700 text-right">{vorgang.quelle}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500">Fällig am</dt>
                <dd className="text-gray-700 text-right">
                  {vorgang.faellig_am ? new Date(vorgang.faellig_am).toLocaleDateString('de-DE') : '–'}
                </dd>
              </div>
              {vorgang.status === 'wiedervorlage' && (
                <div className="flex justify-between gap-3">
                  <dt className="text-gray-500">Wiedervorlage am</dt>
                  <dd className={`text-right ${wiedervorlageUeberfaellig ? 'text-red-600 font-medium' : 'text-gray-700'}`}>
                    {vorgang.wiedervorlage_am ? new Date(vorgang.wiedervorlage_am).toLocaleDateString('de-DE') : '–'}
                  </dd>
                </div>
              )}
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500">Erstellt</dt>
                <dd className="text-gray-700 text-right">
                  {DATUM(vorgang.erstellt_am)}
                  <br /><span className="text-gray-400">von {vorgang.erstellt_von_name ?? '–'}</span>
                </dd>
              </div>
              {vorgang.geschlossen_am && (
                <div className="flex justify-between gap-3">
                  <dt className="text-gray-500">Geschlossen</dt>
                  <dd className="text-gray-700 text-right">
                    {DATUM(vorgang.geschlossen_am)}
                    <br /><span className="text-gray-400">von {vorgang.geschlossen_von_name ?? '–'}</span>
                  </dd>
                </div>
              )}
            </dl>
          </div>

          {/* Dokumente */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <h2 className="font-medium text-gray-800 mb-3">Dokumente</h2>
            <ul className="divide-y divide-gray-100 mb-3">
              {vorgang.dokumente.map(d => {
                // Browser stellen .msg nicht dar und laden es nur herunter —
                // fuer Mails gibt es deshalb zusaetzlich eine Textvorschau.
                const istMail = /\.(eml|msg)$/i.test(d.dateiname)
                return (
                  <li key={d.id} className="py-2 text-sm flex justify-between gap-3">
                    <button
                      type="button"
                      onClick={() => (istMail ? dokumenteApi.openMailVorschau(d.id) : dokumenteApi.openDatei(d.id))}
                      className="text-left text-blue-700 hover:underline truncate"
                      title={istMail ? `${d.dateiname} als Textvorschau oeffnen` : `${d.dateiname} oeffnen`}
                    >
                      {d.dateiname} {d.version > 1 && <span className="text-gray-400">(v{d.version})</span>}
                    </button>
                    <span className="flex items-center gap-3 whitespace-nowrap">
                      {istMail && (
                        <button
                          type="button"
                          onClick={() => dokumenteApi.openDatei(d.id)}
                          className="text-gray-500 hover:text-gray-800 hover:underline text-xs"
                          title="Originaldatei herunterladen"
                        >
                          Original
                        </button>
                      )}
                      <span className="text-gray-400">{DATUM(d.hochgeladen_am)}</span>
                    </span>
                  </li>
                )
              })}
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

          {/* Eigentümer-Portal (selten genutzt → einklappbar) */}
          <Klappbox titel="Eigentümer-Portal">
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
                {portalVorschauOffen ? 'Portal-Vorschau schließen' : 'Portal-Vorschau anzeigen'}
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
          </Klappbox>

        </div>
      </div>
    </div>
  )
}
