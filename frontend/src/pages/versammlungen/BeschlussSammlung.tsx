import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { dokumenteApi } from '../../api/dokumente'
import { objekteApi } from '../../api/objekte'
import { beschlussApi } from '../../api/versammlung'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type { EVAnfechtungStatus, EVBeschluss } from '../../types'

const ANFECHTUNG_OPTIONEN: { value: EVAnfechtungStatus; label: string }[] = [
  { value: 'keine', label: 'Keine Anfechtung bekannt' },
  { value: 'anhaengig', label: 'Anfechtungsklage anhängig' },
  { value: 'abgewiesen', label: 'Klage abgewiesen' },
  { value: 'aufgehoben', label: 'Gerichtlich aufgehoben' },
]

function badgeWert(status: EVAnfechtungStatus) {
  if (status === 'anhaengig') return 'vorschlag'
  if (status === 'aufgehoben') return 'unklar'
  if (status === 'abgewiesen') return 'angenommen'
  return 'archiviert'
}

function AnfechtungForm({ beschluss, onFertig }: {
  beschluss: EVBeschluss
  onFertig: () => void
}) {
  const [status, setStatus] = useState<EVAnfechtungStatus>(beschluss.anfechtung_status)
  const [notiz, setNotiz] = useState(beschluss.anfechtung_notiz)
  const [aufgehobenAm, setAufgehobenAm] = useState(beschluss.aufgehoben_am ?? '')
  const [hinweis, setHinweis] = useState(beschluss.gerichtlicher_hinweis)
  const [fehler, setFehler] = useState('')

  const speichern = useMutation({
    mutationFn: () => beschlussApi.anfechtung(beschluss.id, {
      anfechtung_status: status,
      notiz,
      aufgehoben_am: status === 'aufgehoben' ? (aufgehobenAm || null) : null,
      gerichtlicher_hinweis: hinweis,
    }),
    onSuccess: () => { setFehler(''); onFertig() },
    onError: (e: any) =>
      setFehler(e?.response?.data?.detail ?? 'Speichern fehlgeschlagen.'),
  })

  return (
    <div className="mt-3 space-y-3 rounded border border-gray-200 bg-gray-50 p-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Anfechtungsstatus</label>
          <select
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={status}
            onChange={e => setStatus(e.target.value as EVAnfechtungStatus)}
          >
            {ANFECHTUNG_OPTIONEN.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        {status === 'aufgehoben' && (
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Aufgehoben am</label>
            <input
              type="date"
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={aufgehobenAm}
              onChange={e => setAufgehobenAm(e.target.value)}
            />
          </div>
        )}
      </div>
      <Input label="Notiz (z.B. Gericht und Aktenzeichen)" value={notiz}
        onChange={e => setNotiz(e.target.value)} />
      <Input label="Gerichtlicher Hinweis" value={hinweis}
        onChange={e => setHinweis(e.target.value)} />
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => speichern.mutate()} disabled={speichern.isPending}>
          Vermerk speichern
        </Button>
        <Button size="sm" variant="secondary" onClick={onFertig}>Abbrechen</Button>
      </div>
      <p className="text-xs text-gray-500">
        Der Beschlusswortlaut bleibt unverändert — auch ein aufgehobener
        Beschluss bleibt in der Sammlung stehen (§ 24 Abs. 7 WEG).
      </p>
    </div>
  )
}

function NachtragForm({ objekte, objektVorgabe, onFertig }: {
  objekte: { id: string; bezeichnung: string; objekt_typ?: string }[]
  objektVorgabe: string
  onFertig: () => void
}) {
  const [objekt, setObjekt] = useState(objektVorgabe)
  const [nummer, setNummer] = useState('')
  const [datum, setDatum] = useState('')
  const [ort, setOrt] = useState('')
  const [ueberschrift, setUeberschrift] = useState('')
  const [wortlaut, setWortlaut] = useState('')
  const [ergebnis, setErgebnis] = useState<'angenommen' | 'abgelehnt'>('angenommen')
  const [datei, setDatei] = useState<File | null>(null)
  const [fehler, setFehler] = useState('')

  const speichern = useMutation({
    mutationFn: () => beschlussApi.manuellAnlegen({
      objekt, nummer: nummer.trim() || undefined,
      beschluss_datum: datum, ort, ueberschrift, wortlaut, ergebnis,
      datei,
    }),
    onSuccess: () => { setFehler(''); onFertig() },
    onError: (e: any) => {
      if (e?.response?.status === 403) {
        setFehler('Kein Zugriff — das Nachtragen von Beschlüssen ist nur für '
          + 'Administratoren (is_staff) möglich.')
      } else {
        const data = e?.response?.data
        setFehler(data?.detail
          ?? (typeof data === 'object' ? JSON.stringify(data) : 'Speichern fehlgeschlagen.'))
      }
    },
  })

  const absenden = () => {
    if (!objekt) { setFehler('Bitte ein Objekt wählen.'); return }
    if (!datum) { setFehler('Bitte das Beschlussdatum angeben.'); return }
    if (!wortlaut.trim()) { setFehler('Bitte den Beschlusswortlaut eingeben.'); return }
    speichern.mutate()
  }

  return (
    <div className="space-y-3 rounded border border-primary-200 bg-primary-50/40 p-4">
      <h2 className="font-semibold text-gray-800">Beschluss nachtragen (Bestand)</h2>
      <p className="text-xs text-gray-600">
        Für die Nachpflege bei Objektübernahme — Beschlüsse des Vorverwalters ohne
        Versammlung im System. Nummer leer lassen für die nächste freie Nummer, oder
        die historische Nummer des Vorverwalters eintragen.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Objekt *</label>
          <select
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={objekt}
            onChange={e => setObjekt(e.target.value)}
          >
            <option value="">— wählen —</option>
            {objekte
              .filter(o => o.objekt_typ?.toUpperCase() === 'WEG')
              .map(o => <option key={o.id} value={o.id}>{o.bezeichnung}</option>)}
          </select>
        </div>
        <Input label="Nummer (leer = nächste freie)" type="number" min={1}
          value={nummer} onChange={e => setNummer(e.target.value)} />
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Beschlussdatum *</label>
          <input type="date"
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={datum} onChange={e => setDatum(e.target.value)} />
        </div>
        <Input label="Ort" value={ort} onChange={e => setOrt(e.target.value)} />
      </div>
      <Input label="Überschrift / TOP" value={ueberschrift}
        onChange={e => setUeberschrift(e.target.value)} />
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">Beschlusstext *</label>
        <textarea
          className="min-h-[80px] rounded border border-gray-300 px-3 py-2 text-sm"
          value={wortlaut} onChange={e => setWortlaut(e.target.value)} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Ergebnis</label>
          <select
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={ergebnis}
            onChange={e => setErgebnis(e.target.value as 'angenommen' | 'abgelehnt')}
          >
            <option value="angenommen">Angenommen</option>
            <option value="abgelehnt">Abgelehnt</option>
          </select>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">
          Original-Protokoll (PDF, optional)
        </label>
        <input type="file" accept="application/pdf"
          className="text-sm"
          onChange={e => setDatei(e.target.files?.[0] ?? null)} />
      </div>
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
      <div className="flex gap-2">
        <Button size="sm" onClick={absenden} disabled={speichern.isPending}>
          {speichern.isPending ? 'Speichert…' : 'Beschluss nachtragen'}
        </Button>
        <Button size="sm" variant="secondary" onClick={onFertig}>Abbrechen</Button>
      </div>
      <p className="text-xs text-gray-500">
        Nach dem Anlegen ist der Beschluss unveränderlich (§ 24 Abs. 7 WEG);
        ein eventuelles PDF wird revisionssicher im DMS abgelegt. Folgeaufgaben
        werden bei der Nachpflege bewusst nicht erzeugt.
      </p>
    </div>
  )
}

export function BeschlussSammlung() {
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [objektFilter, setObjektFilter] = useState(searchParams.get('objekt') ?? '')
  const [anfechtungFilter, setAnfechtungFilter] = useState('')
  const [offenesFormular, setOffenesFormular] = useState<string | null>(null)
  const [nachtragOffen, setNachtragOffen] = useState(false)

  const { data: objekte } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
    staleTime: 60_000,
  })

  const params: Record<string, string> = {}
  if (objektFilter) params.objekt = objektFilter
  if (anfechtungFilter) params.anfechtung_status = anfechtungFilter

  const { data: beschluesse, isLoading } = useQuery({
    queryKey: ['beschluesse', params],
    queryFn: () => beschlussApi.list(params),
  })

  const aktualisieren = () => {
    setOffenesFormular(null)
    queryClient.invalidateQueries({ queryKey: ['beschluesse'] })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Beschluss-Sammlung</h1>
          <p className="text-sm text-gray-500">
            Fortlaufend je Objekt nach § 24 Abs. 7 WEG. Einträge werden nie
            gelöscht, der Wortlaut nie geändert.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => setNachtragOffen(v => !v)}>
          {nachtragOffen ? 'Schließen' : '+ Beschluss nachtragen'}
        </Button>
      </div>

      {nachtragOffen && (
        <NachtragForm
          objekte={objekte ?? []}
          objektVorgabe={objektFilter}
          onFertig={() => {
            setNachtragOffen(false)
            queryClient.invalidateQueries({ queryKey: ['beschluesse'] })
          }}
        />
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
            {(objekte ?? [])
              .filter(o => o.objekt_typ?.toUpperCase() === 'WEG')
              .map(o => (
                <option key={o.id} value={o.id}>{o.bezeichnung}</option>
              ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Anfechtung</label>
          <select
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
            value={anfechtungFilter}
            onChange={e => setAnfechtungFilter(e.target.value)}
          >
            <option value="">Alle</option>
            {ANFECHTUNG_OPTIONEN.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && <p className="text-sm text-gray-500">Lädt…</p>}
      {!isLoading && (beschluesse ?? []).length === 0 && (
        <p className="text-sm text-gray-500">Keine Beschlüsse vorhanden.</p>
      )}

      <div className="space-y-3">
        {(beschluesse ?? []).map(b => (
          <div key={b.id} className="rounded border border-gray-200 bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="font-medium text-gray-900">
                  Beschluss {b.nummer} — {b.objekt_bezeichnung}
                </div>
                <div className="text-xs text-gray-500">
                  {new Date(b.beschluss_datum).toLocaleDateString('de-DE')}
                  {b.ort && ` · ${b.ort}`}
                  {b.top_nummer_anzeige !== null && ` · TOP ${b.top_nummer_anzeige}`}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge value={b.ergebnis} label={b.ergebnis_display} />
                <Badge
                  value={badgeWert(b.anfechtung_status)}
                  label={b.anfechtung_status_display}
                />
                {b.dokument && (
                  <Button variant="secondary" size="sm"
                    onClick={() => dokumenteApi.openDatei(b.dokument!)}>
                    PDF
                  </Button>
                )}
                <Button
                  variant="ghost" size="sm"
                  onClick={() => setOffenesFormular(
                    offenesFormular === b.id ? null : b.id,
                  )}
                >
                  Anfechtung
                </Button>
              </div>
            </div>

            <div className="mt-2 border-l-2 border-primary-500 pl-3">
              {b.ueberschrift && (
                <div className="text-sm font-semibold text-gray-900">{b.ueberschrift}</div>
              )}
              <p className="whitespace-pre-line text-sm">{b.wortlaut}</p>
            </div>

            {(b.ev || b.vorgang_nummer) && (
              <div className="mt-2 text-xs text-gray-500">
                {b.ev && (
                  <Link to={`/versammlungen/${b.ev}`} className="text-primary-600 hover:underline">
                    zur Versammlung
                  </Link>
                )}
                {b.ev && b.vorgang_nummer && ' · '}
                {b.vorgang_nummer && (
                  <Link to={`/vorgaenge/${b.vorgang}`} className="text-primary-600 hover:underline">
                    {b.vorgang_nummer}
                  </Link>
                )}
              </div>
            )}

            <div className="mt-1 text-xs text-gray-400">
              Erfasst
              {b.erstellt_von_name && ` von ${b.erstellt_von_name}`}
              {b.erstellt_am && ` am ${new Date(b.erstellt_am).toLocaleDateString('de-DE')}`}
              {!b.ev && ' · Nachtrag (keine Versammlung im System)'}
            </div>

            {b.anfechtung_notiz && (
              <p className="mt-2 text-xs text-amber-700">{b.anfechtung_notiz}</p>
            )}
            {b.aufgehoben_am && (
              <p className="mt-1 text-xs text-red-700">
                Gerichtlich aufgehoben am{' '}
                {new Date(b.aufgehoben_am).toLocaleDateString('de-DE')}
                {b.gerichtlicher_hinweis && ` — ${b.gerichtlicher_hinweis}`}
              </p>
            )}

            {offenesFormular === b.id && (
              <AnfechtungForm beschluss={b} onFertig={aktualisieren} />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
