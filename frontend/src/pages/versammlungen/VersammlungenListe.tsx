import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { objekteApi } from '../../api/objekte'
import { versammlungApi } from '../../api/versammlung'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type { EVArt, EVDetail, EVStimmprinzip } from '../../types'

function fehlertext(error: any, fallback: string) {
  return error?.response?.data?.detail
    ?? (typeof error?.response?.data === 'object'
      ? JSON.stringify(error.response.data)
      : fallback)
}

// ── Stimmgrundlagen-Mehrfachauswahl bei EV-Anlage (Spec v1.1 Kap. 2) ────────
// Die Standard-Stimmgrundlage entsteht bereits automatisch beim Anlegen der
// EV (aus stimmprinzip/stimm_verteilerschluessel, siehe
// stimmgrundlage_service.erzeuge_aus_legacy_feldern) — dieses Panel ergänzt
// nach der Anlage optional weitere Stimmgrundlagen über den bestehenden
// stimmgrundlage-hinzufuegen-Endpunkt.
function ZusatzStimmgrundlagenPanel({ ev, onFertig }: { ev: EVDetail; onFertig: () => void }) {
  const [ausgewaehlt, setAusgewaehlt] = useState<string[]>([])
  const [standard, setStandard] = useState('')
  const [fehler, setFehler] = useState('')

  const { data: verteilerschluessel } = useQuery({
    queryKey: ['verteilerschluessel', ev.objekt],
    queryFn: () => objekteApi.verteilerschluessel({ objekt: ev.objekt }),
    staleTime: 60_000,
  })

  // Verbrauchsschlüssel sind keine zulässige Stimmgrundlage (Spec v1.1 Kap. 2)
  // und bereits vergebene Grundlagen (Kopfprinzip bzw. derselbe
  // Verteilerschlüssel) dürfen wegen der Unique-Constraints je EV nicht
  // doppelt angeboten werden.
  const vorhandeneVsIds = new Set(
    ev.stimmgrundlagen.filter(g => g.verteilerschluessel).map(g => g.verteilerschluessel as string),
  )
  const hatKopfprinzip = ev.stimmgrundlagen.some(g => g.ist_kopfprinzip)

  const optionen: { id: string; label: string }[] = [
    ...(hatKopfprinzip ? [] : [{ id: 'kopf', label: 'Kopfprinzip — eine Stimme je Eigentümer' }]),
    ...(verteilerschluessel ?? [])
      .filter(vs => vs.aktiv && vs.vs_typ !== 'verbrauch' && !vorhandeneVsIds.has(vs.id))
      .map(vs => ({ id: vs.id, label: `${vs.schluessel} ${vs.bezeichnung}` })),
  ]

  const toggle = (id: string) => {
    setAusgewaehlt(alt => (alt.includes(id) ? alt.filter(x => x !== id) : [...alt, id]))
    if (standard === id) setStandard('')
  }

  const speichern = useMutation({
    mutationFn: async () => {
      for (const id of ausgewaehlt) {
        // eslint-disable-next-line no-await-in-loop -- bewusst sequenziell:
        // ist_standard darf serverseitig nur je Aufruf einmal umgesetzt werden.
        await versammlungApi.stimmgrundlageHinzufuegen(ev.id, id === 'kopf'
          ? { ist_kopfprinzip: true, ist_standard: standard === id }
          : { verteilerschluessel: id, ist_standard: standard === id })
      }
    },
    onSuccess: () => {
      setFehler('')
      onFertig()
    },
    onError: (e: any) => setFehler(fehlertext(e, 'Stimmgrundlagen konnten nicht ergänzt werden.')),
  })

  return (
    <div className="space-y-3 rounded border border-gray-200 bg-gray-50 p-4">
      <p className="text-sm text-gray-700">
        „{ev.arbeitsname || ev.art_display}" wurde angelegt — Standard-Stimmgrundlage
        ist „{ev.stimmgrundlagen.find(g => g.ist_standard)?.bezeichnung_anzeige}".
        Weicht die Teilungserklärung für einzelne Tagesordnungspunkte davon ab,
        können hier weitere Stimmgrundlagen ergänzt werden — optional, das
        lässt sich auch später an der Versammlung selbst nachholen.
      </p>
      {optionen.length === 0 && (
        <p className="text-sm text-gray-500">Keine weiteren Stimmgrundlagen verfügbar.</p>
      )}
      <div className="space-y-1">
        {optionen.map(o => (
          <div key={o.id} className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={ausgewaehlt.includes(o.id)}
                onChange={() => toggle(o.id)}
              />
              {o.label}
            </label>
            {ausgewaehlt.includes(o.id) && (
              <label className="flex items-center gap-1 text-xs text-gray-600">
                <input
                  type="radio"
                  name="standard-stimmgrundlage"
                  checked={standard === o.id}
                  onChange={() => setStandard(o.id)}
                />
                als neue Standard-Stimmgrundlage für den ersten TOP
              </label>
            )}
          </div>
        ))}
      </div>
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
      <div className="flex gap-2">
        <Button
          onClick={() => speichern.mutate()}
          disabled={ausgewaehlt.length === 0 || speichern.isPending}
        >
          {speichern.isPending ? 'Speichert…' : 'Stimmgrundlagen ergänzen'}
        </Button>
        <Button variant="secondary" onClick={onFertig}>
          {ausgewaehlt.length === 0 ? 'Fertig' : 'Ohne weitere Stimmgrundlagen fortfahren'}
        </Button>
      </div>
    </div>
  )
}

const STATUS_OPTIONEN = [
  { value: 'entwurf', label: 'Entwurf' },
  { value: 'in_bearbeitung', label: 'In Bearbeitung' },
  { value: 'einladungen_versendet', label: 'Einladungen versendet' },
  { value: 'ausgecheckt', label: 'Ausgecheckt (Abstimmtool)' },
  { value: 'durchgefuehrt', label: 'Durchgeführt (Altdaten)' },
  { value: 'beschluesse_verarbeitet', label: 'Beschlüsse verarbeitet' },
  { value: 'archiviert', label: 'Archiviert' },
]

const ART_OPTIONEN: { value: EVArt; label: string }[] = [
  { value: 'ordentlich', label: 'Ordentliche Versammlung' },
  { value: 'ausserordentl', label: 'Außerordentliche Versammlung' },
  { value: 'wiederholung', label: 'Wiederholungsversammlung' },
]

// Reihenfolge bewusst mit dem gesetzlichen Regelfall zuerst (§ 25 Abs. 2 WEG).
const STIMMPRINZIP_OPTIONEN: { value: EVStimmprinzip; label: string }[] = [
  { value: 'kopf', label: 'Kopfprinzip — eine Stimme je Eigentümer' },
  { value: 'verteilerschluessel', label: 'Nach Verteilerschlüssel (laut Teilungserklärung)' },
]

function terminText(termin: string | null) {
  if (!termin) return '—'
  return new Date(termin).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function VersammlungenListe() {
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()

  const [objektFilter, setObjektFilter] = useState(searchParams.get('objekt') ?? '')
  const [statusFilter, setStatusFilter] = useState('')
  const [formOffen, setFormOffen] = useState(false)
  const [neuAngelegt, setNeuAngelegt] = useState<EVDetail | null>(null)
  const [fehler, setFehler] = useState('')

  const [neuObjekt, setNeuObjekt] = useState(searchParams.get('objekt') ?? '')
  const [neuArbeitsname, setNeuArbeitsname] = useState('')
  const [neuArt, setNeuArt] = useState<EVArt>('ordentlich')
  const [neuStimmprinzip, setNeuStimmprinzip] = useState<EVStimmprinzip>('kopf')
  const [neuVs, setNeuVs] = useState('')

  const { data: objekte } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
    staleTime: 60_000,
  })

  const params: Record<string, string> = {}
  if (objektFilter) params.objekt = objektFilter
  if (statusFilter) params.status = statusFilter

  const { data: versammlungen, isLoading } = useQuery({
    queryKey: ['versammlungen', params],
    queryFn: () => versammlungApi.list(params),
  })

  // Verteilerschlüssel des gewählten Objekts — Grundlage der Stimmkraft, wenn
  // die Teilungserklärung vom Kopfprinzip abweicht.
  const { data: verteilerschluessel } = useQuery({
    queryKey: ['verteilerschluessel', neuObjekt],
    queryFn: () => objekteApi.verteilerschluessel({ objekt: neuObjekt }),
    enabled: Boolean(neuObjekt) && neuStimmprinzip === 'verteilerschluessel',
    staleTime: 60_000,
  })

  const anlegen = useMutation({
    mutationFn: () => versammlungApi.create({
      objekt: neuObjekt,
      arbeitsname: neuArbeitsname,
      art: neuArt,
      stimmprinzip: neuStimmprinzip,
      stimm_verteilerschluessel:
        neuStimmprinzip === 'verteilerschluessel' ? neuVs : null,
    }),
    onSuccess: (ev: EVDetail) => {
      setNeuArbeitsname('')
      setFehler('')
      // Formular bleibt offen — es folgt die optionale Ergänzung weiterer
      // Stimmgrundlagen (Spec v1.1 Kap. 2), erst danach wird geschlossen.
      setNeuAngelegt(ev)
      queryClient.invalidateQueries({ queryKey: ['versammlungen'] })
    },
    onError: (error: any) => {
      setFehler(error?.response?.data?.detail ?? 'Anlage fehlgeschlagen.')
    },
  })

  const formAbschliessen = () => {
    setFormOffen(false)
    setNeuAngelegt(null)
  }

  // Eine EV gibt es nur für WEG — SEV/ZH weist das Backend ab, deshalb hier
  // gar nicht erst anbieten.
  const wegObjekte = (objekte ?? []).filter(o => o.objekt_typ?.toUpperCase() === 'WEG')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Eigentümerversammlungen</h1>
          <p className="text-sm text-gray-500">
            Fünf Tasks von der Terminierung bis zur Beschlussfassung.
          </p>
        </div>
        <Button onClick={() => (formOffen ? formAbschliessen() : setFormOffen(true))}>
          {formOffen ? 'Abbrechen' : 'Versammlung anlegen'}
        </Button>
      </div>

      {formOffen && neuAngelegt && (
        <ZusatzStimmgrundlagenPanel ev={neuAngelegt} onFertig={formAbschliessen} />
      )}

      {formOffen && !neuAngelegt && (
        <div className="rounded border border-gray-200 bg-white p-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Objekt (WEG)</label>
              <select
                className="rounded border border-gray-300 px-3 py-2 text-sm"
                value={neuObjekt}
                onChange={e => setNeuObjekt(e.target.value)}
              >
                <option value="">— bitte wählen —</option>
                {wegObjekte.map(o => (
                  <option key={o.id} value={o.id}>
                    {o.objektnummer} — {o.bezeichnung}
                  </option>
                ))}
              </select>
            </div>
            <Input
              label="Arbeitsname"
              placeholder="z.B. EV 2026 ordentlich"
              value={neuArbeitsname}
              onChange={e => setNeuArbeitsname(e.target.value)}
            />
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Art</label>
              <select
                className="rounded border border-gray-300 px-3 py-2 text-sm"
                value={neuArt}
                onChange={e => setNeuArt(e.target.value as EVArt)}
              >
                {ART_OPTIONEN.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Stimmrecht</label>
              <select
                className="rounded border border-gray-300 px-3 py-2 text-sm"
                value={neuStimmprinzip}
                onChange={e => setNeuStimmprinzip(e.target.value as EVStimmprinzip)}
              >
                {STIMMPRINZIP_OPTIONEN.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            {neuStimmprinzip === 'verteilerschluessel' && (
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-gray-700">
                  Verteilerschlüssel als Stimmgrundlage
                </label>
                <select
                  className="rounded border border-gray-300 px-3 py-2 text-sm"
                  value={neuVs}
                  onChange={e => setNeuVs(e.target.value)}
                  disabled={!neuObjekt}
                >
                  <option value="">— bitte wählen —</option>
                  {(verteilerschluessel ?? [])
                    .filter(vs => vs.aktiv)
                    .map(vs => (
                      <option key={vs.id} value={vs.id}>
                        {vs.schluessel} {vs.bezeichnung}
                      </option>
                    ))}
                </select>
                <p className="text-xs text-gray-500">
                  z.B. „030 Anzahl Einheiten Gesamt" für eine Stimme je Einheit,
                  „031 Anzahl Wohnungen", wenn Stellplätze nicht mitstimmen,
                  oder „010 MEA Gesamt" für das Wertprinzip. Fehlen Werte im
                  Schlüssel, bricht die Teilnehmerermittlung mit Hinweis ab.
                </p>
              </div>
            )}
          </div>

          {fehler && <p className="text-sm text-red-600">{fehler}</p>}

          <div className="flex gap-2">
            <Button
              onClick={() => anlegen.mutate()}
              disabled={
                !neuObjekt || anlegen.isPending
                || (neuStimmprinzip === 'verteilerschluessel' && !neuVs)
              }
            >
              {anlegen.isPending ? 'Wird angelegt…' : 'Anlegen'}
            </Button>
            <Button variant="secondary" onClick={formAbschliessen}>
              Abbrechen
            </Button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Objekt</label>
          <select
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
            value={objektFilter}
            onChange={e => setObjektFilter(e.target.value)}
          >
            <option value="">Alle Objekte</option>
            {wegObjekte.map(o => (
              <option key={o.id} value={o.id}>{o.bezeichnung}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Status</label>
          <select
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
          >
            <option value="">Alle Status</option>
            {STATUS_OPTIONEN.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto rounded border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2">Objekt</th>
              <th className="px-4 py-2">Arbeitsname</th>
              <th className="px-4 py-2">Termin</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2 text-right">Tasks</th>
              <th className="px-4 py-2 text-right">TOP</th>
              <th className="px-4 py-2 text-right">Teilnehmer</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-gray-500">Lädt…</td></tr>
            )}
            {!isLoading && (versammlungen ?? []).length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                  Keine Versammlungen vorhanden.
                </td>
              </tr>
            )}
            {(versammlungen ?? []).map(ev => (
              <tr key={ev.id} className="hover:bg-gray-50">
                <td className="px-4 py-2">
                  <Link to={`/versammlungen/${ev.id}`} className="text-primary-600 hover:underline">
                    {ev.objekt_bezeichnung}
                  </Link>
                  <div className="text-xs text-gray-500">{ev.objektnummer}</div>
                </td>
                <td className="px-4 py-2">{ev.arbeitsname || '—'}</td>
                <td className="px-4 py-2">{terminText(ev.termin)}</td>
                <td className="px-4 py-2">
                  <Badge value={ev.status} label={ev.status_display} />
                </td>
                <td className="px-4 py-2 text-right">{ev.tasks_erledigt} / 5</td>
                <td className="px-4 py-2 text-right">{ev.anzahl_tops}</td>
                <td className="px-4 py-2 text-right">{ev.anzahl_teilnehmer}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
