import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { objekteApi } from '../../api/objekte'
import { versammlungApi } from '../../api/versammlung'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type { EVArt, EVStimmprinzip } from '../../types'

const STATUS_OPTIONEN = [
  { value: 'entwurf', label: 'Entwurf' },
  { value: 'in_bearbeitung', label: 'In Bearbeitung' },
  { value: 'einladungen_versendet', label: 'Einladungen versendet' },
  { value: 'durchgefuehrt', label: 'Durchgeführt' },
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
    onSuccess: () => {
      setFormOffen(false)
      setNeuArbeitsname('')
      setFehler('')
      queryClient.invalidateQueries({ queryKey: ['versammlungen'] })
    },
    onError: (error: any) => {
      setFehler(error?.response?.data?.detail ?? 'Anlage fehlgeschlagen.')
    },
  })

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
        <Button onClick={() => setFormOffen(o => !o)}>
          {formOffen ? 'Abbrechen' : 'Versammlung anlegen'}
        </Button>
      </div>

      {formOffen && (
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
            <Button variant="secondary" onClick={() => setFormOffen(false)}>
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
