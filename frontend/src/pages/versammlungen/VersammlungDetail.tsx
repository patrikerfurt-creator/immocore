import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { dokumenteApi } from '../../api/dokumente'
import { versammlungApi, versammlungDurchfuehrungApi } from '../../api/versammlung'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type {
  EVAbstimmungsmodus, EVAnwesenheitPayload, EVDetail, EVTeilnehmer, EVVersandkanal,
  EVVotum, Tagesordnungspunkt,
} from '../../types'

const MODUS_OPTIONEN: { value: EVAbstimmungsmodus; label: string }[] = [
  { value: 'einfache_mehrheit', label: 'Einfache Mehrheit (Ja > Nein)' },
  { value: 'qualifizierte_mehrheit', label: 'Qualifizierte Mehrheit (Schwelle laut TE)' },
  { value: 'einstimmigkeit', label: 'Einstimmigkeit (alle abgegebenen Stimmen)' },
  { value: 'allstimmigkeit', label: 'Allstimmigkeit (alle Eigentümer)' },
  { value: 'kein_beschluss', label: 'Ohne Beschluss (Bericht/Information)' },
]

const KANAL_OPTIONEN: { value: EVVersandkanal; label: string }[] = [
  { value: 'email', label: 'E-Mail mit PDF' },
  { value: 'epost', label: 'EPost (Postversand)' },
  { value: 'portal', label: 'Portal (noch nicht verfügbar)' },
]

/** ISO-Zeitstempel → Wert für <input type="datetime-local"> (lokale Zeit). */
function isoZuLokal(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function zeit(iso: string | null) {
  return iso ? new Date(iso).toLocaleString('de-DE') : '—'
}

function fehlertext(error: any, fallback: string) {
  return error?.response?.data?.detail
    ?? (typeof error?.response?.data === 'object'
      ? JSON.stringify(error.response.data)
      : fallback)
}

// ── Task 1 ────────────────────────────────────────────────────────────────

function TerminierungPanel({ ev }: { ev: EVDetail }) {
  const queryClient = useQueryClient()
  const [termin, setTermin] = useState(isoZuLokal(ev.termin))
  const [ort, setOrt] = useState(ev.ort)
  const [notizen, setNotizen] = useState(ev.raum_buchung_notizen)
  const [fehler, setFehler] = useState('')

  useEffect(() => {
    setTermin(isoZuLokal(ev.termin))
    setOrt(ev.ort)
    setNotizen(ev.raum_buchung_notizen)
  }, [ev.id, ev.termin, ev.ort, ev.raum_buchung_notizen])

  const speichern = useMutation({
    mutationFn: () => versammlungApi.update(ev.id, {
      termin: termin ? new Date(termin).toISOString() : null,
      ort,
      raum_buchung_notizen: notizen,
    } as Partial<EVDetail>),
    onSuccess: () => {
      setFehler('')
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
    },
    onError: (e: any) => setFehler(fehlertext(e, 'Speichern fehlgeschlagen.')),
  })

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Termin</label>
          <input
            type="datetime-local"
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={termin}
            onChange={e => setTermin(e.target.value)}
          />
        </div>
        <Input
          label="Ort"
          placeholder="z.B. Gemeinschaftsraum EG"
          value={ort}
          onChange={e => setOrt(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">Notizen zur Raumbuchung</label>
        <textarea
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          rows={3}
          value={notizen}
          onChange={e => setNotizen(e.target.value)}
        />
      </div>
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
      <Button onClick={() => speichern.mutate()} disabled={speichern.isPending}>
        {speichern.isPending ? 'Speichert…' : 'Terminierung speichern'}
      </Button>
    </div>
  )
}

// ── Task 2 ────────────────────────────────────────────────────────────────

function TopFormular({ ev, onFertig }: { ev: EVDetail; onFertig: () => void }) {
  const queryClient = useQueryClient()
  const [titel, setTitel] = useState('')
  const [erlaeuterung, setErlaeuterung] = useState('')
  const [vorlage, setVorlage] = useState('')
  const [modus, setModus] = useState<EVAbstimmungsmodus>('einfache_mehrheit')
  const [schwelle, setSchwelle] = useState('66.67')
  const [triggertVorgang, setTriggertVorgang] = useState(false)
  const [triggertWp, setTriggertWp] = useState(false)
  const [fehler, setFehler] = useState('')

  const anlegen = useMutation({
    mutationFn: () => versammlungApi.topAnlegen({
      ev: ev.id,
      titel,
      erlaeuterung,
      beschlussvorlage: vorlage,
      abstimmungsmodus: modus,
      mehrheit_schwelle: modus === 'qualifizierte_mehrheit' ? schwelle : null,
      triggert_vorgang: triggertVorgang,
      triggert_wirtschaftsplan: triggertWp,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
      onFertig()
    },
    onError: (e: any) => setFehler(fehlertext(e, 'TOP konnte nicht angelegt werden.')),
  })

  return (
    <div className="space-y-3 rounded border border-gray-200 bg-gray-50 p-4">
      <Input label="Titel" value={titel} onChange={e => setTitel(e.target.value)} />
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">Erläuterung (optional)</label>
        <textarea
          className="rounded border border-gray-300 px-3 py-2 text-sm" rows={2}
          value={erlaeuterung} onChange={e => setErlaeuterung(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">
          Beschlussvorlage {modus !== 'kein_beschluss' && <span className="text-red-600">*</span>}
        </label>
        <textarea
          className="rounded border border-gray-300 px-3 py-2 text-sm" rows={3}
          placeholder="Der Wortlaut, über den abgestimmt wird."
          value={vorlage} onChange={e => setVorlage(e.target.value)}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Erforderliche Mehrheit</label>
          <select
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={modus}
            onChange={e => setModus(e.target.value as EVAbstimmungsmodus)}
          >
            {MODUS_OPTIONEN.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        {modus === 'qualifizierte_mehrheit' && (
          <Input
            label="Schwelle in % der abgegebenen Stimmen"
            value={schwelle}
            onChange={e => setSchwelle(e.target.value)}
          />
        )}
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={triggertVorgang}
            onChange={e => setTriggertVorgang(e.target.checked)} />
          Bei Annahme Folge-Vorgang anlegen
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={triggertWp}
            onChange={e => setTriggertWp(e.target.checked)} />
          Bei Annahme Wirtschaftsplan-Beschluss vormerken
        </label>
      </div>
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
      <div className="flex gap-2">
        <Button onClick={() => anlegen.mutate()} disabled={!titel || anlegen.isPending}>
          TOP hinzufügen
        </Button>
        <Button variant="secondary" onClick={onFertig}>Abbrechen</Button>
      </div>
    </div>
  )
}

function TagesordnungPanel({ ev }: { ev: EVDetail }) {
  const queryClient = useQueryClient()
  const [formOffen, setFormOffen] = useState(false)
  const [fehler, setFehler] = useState('')

  const { data } = useQuery({
    queryKey: ['versammlung-tagesordnung', ev.id],
    queryFn: () => versammlungApi.tagesordnung(ev.id),
  })

  const loeschen = useMutation({
    mutationFn: (topId: string) => versammlungApi.topLoeschen(topId),
    onSuccess: () => {
      setFehler('')
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
      queryClient.invalidateQueries({ queryKey: ['versammlung-tagesordnung', ev.id] })
    },
    onError: (e: any) => setFehler(fehlertext(e, 'Löschen fehlgeschlagen.')),
  })

  const gesperrt = ['einladungen_versendet', 'durchgefuehrt',
    'beschluesse_verarbeitet', 'archiviert'].includes(ev.status)

  return (
    <div className="space-y-4">
      {gesperrt && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Die Einladung ist versendet — die Tagesordnung ist damit
          festgeschrieben (§ 23 Abs. 2 WEG). Nur Erläuterungen sind noch
          änderbar.
        </p>
      )}

      {(data?.probleme ?? []).length > 0 && (
        <ul className="rounded border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-800 list-disc list-inside">
          {data!.probleme.map(p => <li key={p}>{p}</li>)}
        </ul>
      )}

      {fehler && <p className="text-sm text-red-600">{fehler}</p>}

      <div className="space-y-3">
        {(data?.tagesordnung ?? []).map((top: Tagesordnungspunkt) => (
          <div key={top.id} className="rounded border border-gray-200 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-medium text-gray-900">
                  TOP {top.nummer}: {top.titel}
                </div>
                {top.erlaeuterung && (
                  <p className="mt-1 whitespace-pre-line text-sm text-gray-600">
                    {top.erlaeuterung}
                  </p>
                )}
                {top.beschlussvorlage && (
                  <p className="mt-2 border-l-2 border-primary-500 pl-2 whitespace-pre-line text-sm">
                    {top.beschlussvorlage}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <span>{top.abstimmungsmodus_display}</span>
                  {top.mehrheit_schwelle && <span>· {top.mehrheit_schwelle} %</span>}
                  {top.triggert_vorgang && <Badge value="vorschlag" label="Folge-Vorgang" />}
                  {top.triggert_wirtschaftsplan && <Badge value="vorschlag" label="WP-Beschluss" />}
                  {top.abstimmungsergebnis !== 'offen' && (
                    <Badge
                      value={top.abstimmungsergebnis === 'angenommen' ? 'angenommen' : 'abgelehnt'}
                      label={top.abstimmungsergebnis_display}
                    />
                  )}
                </div>
              </div>
              {!gesperrt && (
                <Button
                  variant="ghost" size="sm"
                  onClick={() => loeschen.mutate(top.id)}
                >
                  Löschen
                </Button>
              )}
            </div>
          </div>
        ))}
        {(data?.tagesordnung ?? []).length === 0 && (
          <p className="text-sm text-gray-500">Noch kein Tagesordnungspunkt erfasst.</p>
        )}
      </div>

      {!gesperrt && (formOffen
        ? <TopFormular ev={ev} onFertig={() => setFormOffen(false)} />
        : <Button onClick={() => setFormOffen(true)}>TOP hinzufügen</Button>)}
    </div>
  )
}

// ── Teilnehmer ────────────────────────────────────────────────────────────

function TeilnehmerPanel({ ev }: { ev: EVDetail }) {
  const queryClient = useQueryClient()
  const [fehler, setFehler] = useState('')
  const [ergebnis, setErgebnis] = useState('')

  const { data: teilnehmer } = useQuery({
    queryKey: ['versammlung-teilnehmer', ev.id],
    queryFn: () => versammlungApi.teilnehmer(ev.id),
  })

  const ermitteln = useMutation({
    mutationFn: () => versammlungApi.teilnehmerErmitteln(ev.id),
    onSuccess: daten => {
      setFehler('')
      setErgebnis(
        `${daten.teilnehmer} Teilnehmer (${daten.neu} neu, ${daten.entfallen} nicht `
        + `mehr stimmberechtigt), Gesamtstimmkraft ${daten.gesamt_stimmkraft} `
        + `nach "${daten.grundlage}".`
        + (daten.ohne_stimmrecht.length
          ? ` Ohne Stimmrecht in diesem Schlüssel: ${daten.ohne_stimmrecht.join(', ')}.`
          : ''),
      )
      queryClient.invalidateQueries({ queryKey: ['versammlung-teilnehmer', ev.id] })
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
    },
    onError: (e: any) => {
      setErgebnis('')
      setFehler(fehlertext(e, 'Teilnehmer konnten nicht ermittelt werden.'))
    },
  })

  const gesamt = (teilnehmer ?? []).reduce((s, t) => s + Number(t.stimmkraft), 0)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => ermitteln.mutate()} disabled={ermitteln.isPending}>
          {ermitteln.isPending ? 'Ermittelt…' : 'Teilnehmer und Stimmkraft ermitteln'}
        </Button>
        <span className="text-sm text-gray-500">
          Grundlage: {ev.stimm_verteilerschluessel_text ?? ev.stimmprinzip_display}
        </span>
      </div>
      {ergebnis && <p className="text-sm text-green-700">{ergebnis}</p>}
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}

      {(teilnehmer ?? []).length > 0 && (
        <div className="overflow-x-auto rounded border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2">Eigentümer</th>
                <th className="px-3 py-2">Einheiten</th>
                <th className="px-3 py-2 text-right">Stimmkraft</th>
                <th className="px-3 py-2">Zusage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(teilnehmer ?? []).map(t => (
                <tr key={t.id} className={Number(t.stimmkraft) === 0 ? 'text-gray-400' : ''}>
                  <td className="px-3 py-2">{t.person_name}</td>
                  <td className="px-3 py-2">
                    {t.anteile.map(a => a.einheit_nr_snapshot).join(', ') || '—'}
                  </td>
                  <td className="px-3 py-2 text-right">{t.stimmkraft}</td>
                  <td className="px-3 py-2">
                    <Badge
                      value={t.zusage_status === 'zugesagt' ? 'angenommen'
                        : t.zusage_status === 'abgesagt' ? 'abgelehnt' : 'offen'}
                      label={t.zusage_status}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 text-sm font-medium">
              <tr>
                <td className="px-3 py-2" colSpan={2}>Gesamtstimmkraft</td>
                <td className="px-3 py-2 text-right">{gesamt}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Task 3 ────────────────────────────────────────────────────────────────

function EinladungPanel({ ev }: { ev: EVDetail }) {
  const queryClient = useQueryClient()
  const [einladungstext, setEinladungstext] = useState(ev.einladungstext)
  const [anlagen, setAnlagen] = useState<string[]>([])
  const [plan, setPlan] = useState<Record<string, EVVersandkanal>>({})
  const [sofort, setSofort] = useState(false)
  const [meldung, setMeldung] = useState('')
  const [fehler, setFehler] = useState('')

  useEffect(() => setEinladungstext(ev.einladungstext), [ev.id, ev.einladungstext])

  const { data: dokumente } = useQuery({
    queryKey: ['objekt-dokumente', ev.objekt],
    queryFn: () => dokumenteApi.listByObjekt(ev.objekt),
    staleTime: 30_000,
  })
  const { data: versandplan } = useQuery({
    queryKey: ['versammlung-versandplan', ev.id],
    queryFn: () => versammlungApi.versandplan(ev.id),
  })
  const { data: protokoll } = useQuery({
    queryKey: ['versammlung-versandprotokoll', ev.id],
    queryFn: () => versammlungApi.versandprotokoll(ev.id),
  })

  const pdfAnlagen = useMemo(
    () => (dokumente ?? []).filter(d => d.dateiname?.toLowerCase().endsWith('.pdf')),
    [dokumente],
  )

  const textSpeichern = useMutation({
    mutationFn: () => versammlungApi.update(ev.id, { einladungstext } as Partial<EVDetail>),
    onSuccess: () => {
      setMeldung('Einladungstext gespeichert.')
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
    },
    onError: (e: any) => setFehler(fehlertext(e, 'Speichern fehlgeschlagen.')),
  })

  const pdfErzeugen = useMutation({
    mutationFn: () => versammlungApi.einladungPdfErzeugen(ev.id, anlagen),
    onSuccess: daten => {
      setFehler('')
      setMeldung(`Einladungs-PDF erzeugt: ${daten.dateiname}`)
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
    },
    onError: (e: any) => {
      setMeldung('')
      setFehler(fehlertext(e, 'PDF-Erzeugung fehlgeschlagen.'))
    },
  })

  const versenden = useMutation({
    mutationFn: () => versammlungApi.einladungenVersenden(ev.id, plan, sofort),
    onSuccess: ({ status, daten }) => {
      setFehler('')
      if (status === 202) {
        setMeldung((daten as any).detail)
      } else {
        const e = daten as any
        setMeldung(
          `${e.erfolgreich} von ${e.gesamt} versendet — E-Mail ${e.kanaele.email}, `
          + `EPost ${e.kanaele.epost}, fehlgeschlagen ${e.fehlgeschlagen}, `
          + `übersprungen ${e.uebersprungen}.`
          + (e.epost_ordner ? ` EPost-Ordner: ${e.epost_ordner}` : ''),
        )
      }
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
      queryClient.invalidateQueries({ queryKey: ['versammlung-versandprotokoll', ev.id] })
    },
    onError: (e: any) => {
      setMeldung('')
      setFehler(fehlertext(e, 'Versand fehlgeschlagen.'))
    },
  })

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700">Einladungstext</label>
        <textarea
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
          rows={8}
          value={einladungstext}
          onChange={e => setEinladungstext(e.target.value)}
        />
        <Button
          variant="secondary" size="sm"
          onClick={() => textSpeichern.mutate()} disabled={textSpeichern.isPending}
        >
          Text speichern
        </Button>
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium text-gray-700">
          Anlagen (nur PDF, aus der Objektakte)
        </div>
        {pdfAnlagen.length === 0 && (
          <p className="text-sm text-gray-500">Keine PDF-Dokumente am Objekt.</p>
        )}
        <div className="max-h-40 space-y-1 overflow-y-auto">
          {pdfAnlagen.map(d => (
            <label key={d.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={anlagen.includes(d.id)}
                onChange={e => setAnlagen(alt => e.target.checked
                  ? [...alt, d.id]
                  : alt.filter(id => id !== d.id))}
              />
              {d.dateiname}
              <span className="text-xs text-gray-500">{d.kategorie}</span>
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => pdfErzeugen.mutate()} disabled={pdfErzeugen.isPending}>
            {pdfErzeugen.isPending ? 'Erzeugt…' : 'Einladungs-PDF erzeugen'}
          </Button>
          {ev.einladungs_pdf && (
            <Button
              variant="secondary" size="sm"
              onClick={() => dokumenteApi.openDatei(ev.einladungs_pdf!)}
            >
              {ev.einladungs_pdf_dateiname ?? 'PDF'} öffnen
            </Button>
          )}
        </div>
      </div>

      {versandplan && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-gray-700">Versandplan</div>
          {!versandplan.portal_verfuegbar && (
            <p className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
              {versandplan.portal_hinweis}
            </p>
          )}
          {!versandplan.ladungsfrist.eingehalten && versandplan.ladungsfrist.warnung && (
            <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {versandplan.ladungsfrist.warnung}
            </p>
          )}
          <div className="overflow-x-auto rounded border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2">Eigentümer</th>
                  <th className="px-3 py-2">Empfänger</th>
                  <th className="px-3 py-2">Kanal</th>
                  <th className="px-3 py-2">Hinweis</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {versandplan.eintraege.map(e => (
                  <tr key={e.teilnehmer_id}>
                    <td className="px-3 py-2">
                      {e.name}
                      {e.nicht_stimmberechtigt && (
                        <span className="ml-2 text-xs text-gray-400">(ohne Stimmkraft)</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-gray-600">{e.empfaenger || '—'}</td>
                    <td className="px-3 py-2">
                      <select
                        className="rounded border border-gray-300 px-2 py-1 text-sm"
                        value={plan[e.teilnehmer_id] ?? e.kanal}
                        onChange={ev2 => setPlan(alt => ({
                          ...alt, [e.teilnehmer_id]: ev2.target.value as EVVersandkanal,
                        }))}
                      >
                        {KANAL_OPTIONEN.map(o => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2 text-xs text-amber-700">{e.hinweis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox" checked={sofort}
                onChange={e => setSofort(e.target.checked)}
              />
              Sofort versenden (nur für kleine Gemeinschaften — sonst im Hintergrund)
            </label>
            <Button
              onClick={() => versenden.mutate()}
              disabled={!ev.einladungs_pdf || versenden.isPending}
            >
              {versenden.isPending ? 'Versendet…' : 'Einladungen versenden'}
            </Button>
          </div>
        </div>
      )}

      {meldung && <p className="text-sm text-green-700">{meldung}</p>}
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}

      {(protokoll ?? []).length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-gray-700">Versandprotokoll</div>
          <div className="overflow-x-auto rounded border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2">Zeit</th>
                  <th className="px-3 py-2">Eigentümer</th>
                  <th className="px-3 py-2">Kanal</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Empfänger / Fehler</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(protokoll ?? []).map(p => (
                  <tr key={p.id}>
                    <td className="px-3 py-2 text-gray-500">{zeit(p.versendet_am)}</td>
                    <td className="px-3 py-2">{p.person_name}</td>
                    <td className="px-3 py-2">{p.kanal_display}</td>
                    <td className="px-3 py-2">
                      <Badge
                        value={p.status === 'erfolgreich' ? 'angenommen'
                          : p.status === 'fehlgeschlagen' ? 'fehlgeschlagen' : 'ignoriert'}
                        label={p.status}
                      />
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {p.fehlertext || p.epost_pfad || p.empfaenger}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Task 4 ────────────────────────────────────────────────────────────────

function AnwesenheitZeile({ teilnehmer, alle, onGeaendert }: {
  teilnehmer: EVTeilnehmer
  alle: EVTeilnehmer[]
  onGeaendert: () => void
}) {
  const [fehler, setFehler] = useState('')

  const setzen = useMutation({
    mutationFn: (daten: EVAnwesenheitPayload) =>
      versammlungDurchfuehrungApi.anwesenheit(teilnehmer.id, daten),
    onSuccess: () => { setFehler(''); onGeaendert() },
    onError: (e: any) => setFehler(fehlertext(e, 'Speichern fehlgeschlagen.')),
  })

  const knopf = (wert: boolean | null, label: string) => {
    const aktiv = teilnehmer.ist_anwesend === wert
    return (
      <button
        type="button"
        onClick={() => setzen.mutate({ ist_anwesend: wert })}
        className={`rounded border px-2 py-1 text-xs ${
          aktiv
            ? 'border-primary-500 bg-primary-50 font-medium text-primary-700'
            : 'border-gray-300 text-gray-600 hover:bg-gray-50'
        }`}
      >
        {label}
      </button>
    )
  }

  return (
    <tr className={Number(teilnehmer.stimmkraft) === 0 ? 'text-gray-400' : ''}>
      <td className="px-3 py-2">
        {teilnehmer.person_name}
        {fehler && <div className="text-xs text-red-600">{fehler}</div>}
      </td>
      <td className="px-3 py-2 text-xs text-gray-500">
        {teilnehmer.anteile.map(a => a.einheit_nr_snapshot).join(', ') || '—'}
      </td>
      <td className="px-3 py-2 text-right">{teilnehmer.stimmkraft}</td>
      <td className="px-3 py-2">
        <div className="flex gap-1">
          {knopf(true, 'anwesend')}
          {knopf(false, 'abwesend')}
          {knopf(null, 'offen')}
        </div>
      </td>
      <td className="px-3 py-2">
        <select
          className="rounded border border-gray-300 px-2 py-1 text-xs"
          value={teilnehmer.vertreten_durch ?? ''}
          onChange={e => setzen.mutate({
            vertreten_durch: e.target.value || null,
          })}
        >
          <option value="">keine Vertretung</option>
          {alle
            .filter(t => t.person !== teilnehmer.person)
            .map(t => (
              <option key={t.id} value={t.person}>{t.person_name}</option>
            ))}
        </select>
      </td>
    </tr>
  )
}

function AbstimmungBlock({ top, teilnehmer, onGeaendert }: {
  top: Tagesordnungspunkt
  teilnehmer: EVTeilnehmer[]
  onGeaendert: () => void
}) {
  const [ja, setJa] = useState(top.abstimmung_ja)
  const [nein, setNein] = useState(top.abstimmung_nein)
  const [enthaltung, setEnthaltung] = useState(top.abstimmung_enthaltung)
  const [bemerkung, setBemerkung] = useState(top.ergebnis_bemerkung)
  const [namentlich, setNamentlich] = useState(false)
  const [voten, setVoten] = useState<Record<string, EVVotum>>({})
  const [fehler, setFehler] = useState('')

  const anwesende = teilnehmer.filter(t => t.ist_anwesend === true)

  const erfassen = useMutation({
    mutationFn: () => versammlungDurchfuehrungApi.abstimmung(
      top.id, ja, nein, enthaltung, bemerkung,
    ),
    onSuccess: () => { setFehler(''); onGeaendert() },
    onError: (e: any) => setFehler(fehlertext(e, 'Erfassen fehlgeschlagen.')),
  })

  const erfassenNamentlich = useMutation({
    mutationFn: () => versammlungDurchfuehrungApi.einzelstimmen(top.id, voten),
    onSuccess: daten => {
      setFehler('')
      setJa(daten.abstimmung_ja)
      setNein(daten.abstimmung_nein)
      setEnthaltung(daten.abstimmung_enthaltung)
      onGeaendert()
    },
    onError: (e: any) => setFehler(fehlertext(e, 'Erfassen fehlgeschlagen.')),
  })

  const statusSetzen = useMutation({
    mutationFn: (ergebnis: 'vertagt' | 'entfallen') =>
      versammlungDurchfuehrungApi.ergebnisStatus(top.id, ergebnis, bemerkung),
    onSuccess: () => { setFehler(''); onGeaendert() },
    onError: (e: any) => setFehler(fehlertext(e, 'Speichern fehlgeschlagen.')),
  })

  if (top.abstimmungsmodus === 'kein_beschluss') {
    return (
      <div className="rounded border border-gray-200 p-3">
        <div className="font-medium text-gray-900">TOP {top.nummer}: {top.titel}</div>
        <p className="mt-1 text-sm text-gray-500">
          Ohne Beschlussfassung — hier ist nichts zu erfassen.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded border border-gray-200 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium text-gray-900">TOP {top.nummer}: {top.titel}</div>
          <div className="text-xs text-gray-500">
            {top.abstimmungsmodus_display}
            {top.mehrheit_schwelle && ` · Schwelle ${top.mehrheit_schwelle} %`}
          </div>
        </div>
        {top.abstimmungsergebnis !== 'offen' && (
          <Badge
            value={top.abstimmungsergebnis === 'angenommen' ? 'angenommen'
              : top.abstimmungsergebnis === 'abgelehnt' ? 'abgelehnt' : 'wiedervorlage'}
            label={top.abstimmungsergebnis_display}
          />
        )}
      </div>

      <p className="mt-2 border-l-2 border-primary-500 pl-2 text-sm whitespace-pre-line">
        {top.beschlussvorlage}
      </p>

      {!namentlich ? (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Input label="Ja" className="w-24" value={ja} onChange={e => setJa(e.target.value)} />
          <Input label="Nein" className="w-24" value={nein} onChange={e => setNein(e.target.value)} />
          <Input label="Enthaltung" className="w-28" value={enthaltung}
            onChange={e => setEnthaltung(e.target.value)} />
          <Button size="sm" onClick={() => erfassen.mutate()} disabled={erfassen.isPending}>
            Ergebnis erfassen
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-1">
          {anwesende.length === 0 && (
            <p className="text-sm text-amber-700">
              Es ist niemand als anwesend erfasst — namentliche Abstimmung nicht möglich.
            </p>
          )}
          {anwesende.map(t => (
            <div key={t.id} className="flex items-center gap-3 text-sm">
              <span className="w-56 truncate">{t.person_name}</span>
              <span className="w-12 text-right text-gray-500">{t.stimmkraft}</span>
              <select
                className="rounded border border-gray-300 px-2 py-1 text-xs"
                value={voten[t.id] ?? ''}
                onChange={e => setVoten(alt => {
                  const neu = { ...alt }
                  if (e.target.value) neu[t.id] = e.target.value as EVVotum
                  else delete neu[t.id]
                  return neu
                })}
              >
                <option value="">— nicht abgegeben —</option>
                <option value="ja">Ja</option>
                <option value="nein">Nein</option>
                <option value="enthaltung">Enthaltung</option>
              </select>
            </div>
          ))}
          {anwesende.length > 0 && (
            <Button
              size="sm" className="mt-2"
              onClick={() => erfassenNamentlich.mutate()}
              disabled={erfassenNamentlich.isPending || Object.keys(voten).length === 0}
            >
              Namentliche Abstimmung erfassen
            </Button>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-gray-600">
          <input type="checkbox" checked={namentlich}
            onChange={e => setNamentlich(e.target.checked)} />
          namentlich abstimmen
        </label>
        <Button variant="secondary" size="sm" onClick={() => statusSetzen.mutate('vertagt')}>
          Vertagen
        </Button>
        <Button variant="secondary" size="sm" onClick={() => statusSetzen.mutate('entfallen')}>
          Entfallen
        </Button>
      </div>

      <div className="mt-2">
        <Input
          label="Bemerkung zum Ergebnis"
          value={bemerkung}
          onChange={e => setBemerkung(e.target.value)}
        />
      </div>

      {fehler && <p className="mt-2 text-sm text-red-600">{fehler}</p>}
    </div>
  )
}

function DurchfuehrungPanel({ ev }: { ev: EVDetail }) {
  const queryClient = useQueryClient()
  const [meldung, setMeldung] = useState('')
  const [fehler, setFehler] = useState('')

  const { data: teilnehmer } = useQuery({
    queryKey: ['versammlung-teilnehmer', ev.id],
    queryFn: () => versammlungApi.teilnehmer(ev.id),
  })
  const { data: quorum } = useQuery({
    queryKey: ['versammlung-quorum', ev.id],
    queryFn: () => versammlungDurchfuehrungApi.quorum(ev.id),
  })

  const aktualisieren = () => {
    queryClient.invalidateQueries({ queryKey: ['versammlung-teilnehmer', ev.id] })
    queryClient.invalidateQueries({ queryKey: ['versammlung-quorum', ev.id] })
    queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
    queryClient.invalidateQueries({ queryKey: ['versammlung-ereignisse', ev.id] })
  }

  const abschliessen = useMutation({
    mutationFn: () => versammlungDurchfuehrungApi.durchfuehrungAbschliessen(ev.id),
    onSuccess: () => {
      setFehler('')
      setMeldung('Durchführung abgeschlossen.')
      aktualisieren()
    },
    onError: (e: any) => {
      setMeldung('')
      setFehler(fehlertext(e, 'Abschluss fehlgeschlagen.'))
    },
  })

  const gesperrt = ['beschluesse_verarbeitet', 'archiviert'].includes(ev.status)

  return (
    <div className="space-y-6">
      {gesperrt && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Die Beschlüsse sind verarbeitet — Anwesenheit und Ergebnisse sind
          nicht mehr änderbar.
        </p>
      )}

      {quorum && (
        <div className="rounded border border-gray-200 bg-gray-50 p-3 text-sm">
          <div className="font-medium text-gray-900">
            Anwesend: {quorum.anwesende_stimmkraft} von {quorum.gesamt_stimmkraft} Stimmen
            ({quorum.anwesend_prozent} %) — {quorum.anzahl_anwesend} von{' '}
            {quorum.anzahl_teilnehmer} Eigentümern
          </div>
          {quorum.anzahl_anwesenheit_offen > 0 && (
            <div className="mt-1 text-xs text-amber-700">
              Bei {quorum.anzahl_anwesenheit_offen} Teilnehmern ist die Anwesenheit
              noch nicht erfasst.
            </div>
          )}
          <div className="mt-1 text-xs text-gray-500">{quorum.hinweis}</div>
        </div>
      )}

      <div>
        <div className="mb-2 text-sm font-medium text-gray-700">Anwesenheit</div>
        <div className="overflow-x-auto rounded border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2">Eigentümer</th>
                <th className="px-3 py-2">Einheiten</th>
                <th className="px-3 py-2 text-right">Stimmen</th>
                <th className="px-3 py-2">Anwesenheit</th>
                <th className="px-3 py-2">Vertreten durch</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(teilnehmer ?? []).map(t => (
                <AnwesenheitZeile
                  key={t.id} teilnehmer={t} alle={teilnehmer ?? []}
                  onGeaendert={aktualisieren}
                />
              ))}
              {(teilnehmer ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-gray-500">
                    Noch keine Teilnehmer ermittelt — siehe Task 3.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-3">
        <div className="text-sm font-medium text-gray-700">Abstimmungen</div>
        {ev.tagesordnung.map(top => (
          <AbstimmungBlock
            key={top.id} top={top} teilnehmer={teilnehmer ?? []}
            onGeaendert={aktualisieren}
          />
        ))}
        {ev.tagesordnung.length === 0 && (
          <p className="text-sm text-gray-500">Keine Tagesordnungspunkte vorhanden.</p>
        )}
      </div>

      {meldung && <p className="text-sm text-green-700">{meldung}</p>}
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}

      <Button
        onClick={() => abschliessen.mutate()}
        disabled={abschliessen.isPending || gesperrt}
      >
        Durchführung abschließen
      </Button>
    </div>
  )
}

// ── Task 5 ────────────────────────────────────────────────────────────────

function BeschlussfassungPanel({ ev }: { ev: EVDetail }) {
  const queryClient = useQueryClient()
  const [meldung, setMeldung] = useState('')
  const [fehler, setFehler] = useState('')

  const { data: beschluesse } = useQuery({
    queryKey: ['versammlung-beschluesse', ev.id],
    queryFn: () => versammlungDurchfuehrungApi.beschluesseDerEv(ev.id),
  })

  const uebernehmen = useMutation({
    mutationFn: () => versammlungDurchfuehrungApi.beschluesseUebernehmen(ev.id),
    onSuccess: daten => {
      setFehler('')
      setMeldung(
        `${daten.beschluesse} Beschluss/Beschlüsse übernommen`
        + (daten.uebersprungen ? `, ${daten.uebersprungen} bereits vorhanden` : '')
        + `, ${daten.vorgaenge} Folgeaufgabe(n) angelegt.`,
      )
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
      queryClient.invalidateQueries({ queryKey: ['versammlung-beschluesse', ev.id] })
      queryClient.invalidateQueries({ queryKey: ['versammlung-ereignisse', ev.id] })
    },
    onError: (e: any) => {
      setMeldung('')
      setFehler(fehlertext(e, 'Übernahme fehlgeschlagen.'))
    },
  })

  const protokoll = useMutation({
    mutationFn: () => versammlungDurchfuehrungApi.protokollErzeugen(ev.id),
    onSuccess: daten => {
      setFehler('')
      setMeldung(`Protokoll erzeugt: ${daten.dateiname}`)
      queryClient.invalidateQueries({ queryKey: ['versammlung', ev.id] })
    },
    onError: (e: any) => setFehler(fehlertext(e, 'Protokoll fehlgeschlagen.')),
  })

  const angenommen = ev.tagesordnung.filter(t => t.abstimmungsergebnis === 'angenommen')

  return (
    <div className="space-y-6">
      <div className="rounded border border-gray-200 bg-gray-50 p-3 text-sm">
        {angenommen.length === 0
          ? 'Kein angenommener Tagesordnungspunkt — es entsteht kein Beschluss.'
          : `${angenommen.length} angenommene(r) TOP wird in die Beschluss-Sammlung `
            + 'nach § 24 Abs. 7 WEG übernommen. Je Beschluss entsteht ein '
            + 'revisionssicheres PDF; konfigurierte Folgeaufgaben werden als '
            + 'Vorgang angelegt.'}
      </div>

      <div className="flex flex-wrap gap-3">
        <Button
          onClick={() => uebernehmen.mutate()}
          disabled={uebernehmen.isPending || ev.status === 'archiviert'}
        >
          {uebernehmen.isPending ? 'Übernimmt…' : 'Beschlüsse übernehmen und Protokoll erzeugen'}
        </Button>
        <Button
          variant="secondary"
          onClick={() => protokoll.mutate()}
          disabled={protokoll.isPending}
        >
          Protokoll neu erzeugen
        </Button>
        {ev.protokoll_pdf && (
          <Button
            variant="secondary"
            onClick={() => dokumenteApi.openDatei(ev.protokoll_pdf!)}
          >
            Protokoll öffnen
          </Button>
        )}
      </div>

      {meldung && <p className="text-sm text-green-700">{meldung}</p>}
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}

      {(beschluesse ?? []).length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-gray-700">
            Beschlüsse dieser Versammlung
          </div>
          {(beschluesse ?? []).map(b => (
            <div key={b.id} className="rounded border border-gray-200 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="font-medium text-gray-900">
                  Beschluss {b.nummer}
                  {b.top_nummer !== null && ` (TOP ${b.top_nummer})`}
                </div>
                <div className="flex items-center gap-2">
                  {b.anfechtung_status !== 'keine' && (
                    <Badge value="unklar" label={b.anfechtung_status_display} />
                  )}
                  {b.dokument && (
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => dokumenteApi.openDatei(b.dokument!)}
                    >
                      PDF
                    </Button>
                  )}
                </div>
              </div>
              <p className="mt-1 whitespace-pre-line text-sm">{b.wortlaut}</p>
              <div className="mt-2 text-xs text-gray-500">
                Ja {b.ergebnis_ja} · Nein {b.ergebnis_nein} · Enthaltung{' '}
                {b.ergebnis_enthaltung}
                {b.vorgang_nummer && (
                  <> · Folgeaufgabe{' '}
                    <Link to={`/vorgaenge/${b.vorgang}`} className="text-primary-600 hover:underline">
                      {b.vorgang_nummer}
                    </Link>
                  </>
                )}
              </div>
            </div>
          ))}
          <Link
            to={`/versammlungen/beschluesse?objekt=${ev.objekt}`}
            className="inline-block text-sm text-primary-600 hover:underline"
          >
            Zur Beschluss-Sammlung des Objekts →
          </Link>
        </div>
      )}
    </div>
  )
}

// ── Seite ─────────────────────────────────────────────────────────────────

const TASK_TITEL: Record<number, string> = {
  1: 'Terminierung', 2: 'Tagesordnung', 3: 'Einladung',
  4: 'Durchführung', 5: 'Beschlussfassung',
}

export function VersammlungDetail() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const [aktiverTask, setAktiverTask] = useState(1)
  const [taskFehler, setTaskFehler] = useState('')

  const { data: ev, isLoading } = useQuery({
    queryKey: ['versammlung', id],
    queryFn: () => versammlungApi.get(id),
    enabled: Boolean(id),
  })
  const { data: ereignisse } = useQuery({
    queryKey: ['versammlung-ereignisse', id],
    queryFn: () => versammlungApi.ereignisse(id),
    enabled: Boolean(id),
  })

  const taskErledigt = useMutation({
    mutationFn: (taskNr: number) => versammlungApi.taskErledigt(id, taskNr),
    onSuccess: () => {
      setTaskFehler('')
      queryClient.invalidateQueries({ queryKey: ['versammlung', id] })
      queryClient.invalidateQueries({ queryKey: ['versammlung-ereignisse', id] })
    },
    onError: (e: any) => setTaskFehler(fehlertext(e, 'Task konnte nicht abgeschlossen werden.')),
  })

  const taskZuruecksetzen = useMutation({
    mutationFn: ({ taskNr, grund }: { taskNr: number; grund: string }) =>
      versammlungApi.taskZuruecksetzen(id, taskNr, grund),
    onSuccess: () => {
      setTaskFehler('')
      queryClient.invalidateQueries({ queryKey: ['versammlung', id] })
      queryClient.invalidateQueries({ queryKey: ['versammlung-ereignisse', id] })
    },
    onError: (e: any) => setTaskFehler(fehlertext(e, 'Rücksetzen fehlgeschlagen.')),
  })

  if (isLoading || !ev) {
    return <p className="text-sm text-gray-500">Lädt…</p>
  }

  const taskStatus = ev.task_status
  const tasks = [1, 2, 3, 4, 5].map(nr => ({
    nr,
    titel: TASK_TITEL[nr],
    erledigt: (taskStatus as any)[`task${nr}`].erledigt as boolean,
  }))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/versammlungen" className="text-sm text-primary-600 hover:underline">
            ← Alle Versammlungen
          </Link>
          <h1 className="mt-1 text-xl font-semibold text-gray-900">
            {ev.arbeitsname || ev.art_display}
          </h1>
          <p className="text-sm text-gray-500">
            {ev.objekt_bezeichnung} ({ev.objektnummer}) ·{' '}
            {ev.stimm_verteilerschluessel_text
              ? `Stimmen nach ${ev.stimm_verteilerschluessel_text}`
              : ev.stimmprinzip_display}
          </p>
        </div>
        <div className="text-right">
          <Badge value={ev.status} label={ev.status_display} />
          <p className="mt-1 text-sm text-gray-500">
            {ev.termin ? new Date(ev.termin).toLocaleString('de-DE') : 'ohne Termin'}
            {ev.ort && ` · ${ev.ort}`}
          </p>
        </div>
      </div>

      {!ev.ladungsfrist.eingehalten && ev.ladungsfrist.warnung && ev.termin && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {ev.ladungsfrist.warnung}
        </p>
      )}

      <div className="grid gap-2 md:grid-cols-5">
        {tasks.map(t => (
          <button
            key={t.nr}
            type="button"
            onClick={() => setAktiverTask(t.nr)}
            className={`rounded border p-3 text-left transition ${
              aktiverTask === t.nr
                ? 'border-primary-500 bg-primary-50'
                : 'border-gray-200 bg-white hover:bg-gray-50'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-gray-500">
                Task {t.nr}
              </span>
              <span>{t.erledigt ? '✅' : '⬜'}</span>
            </div>
            <div className="mt-1 text-sm font-medium text-gray-900">{t.titel}</div>
          </button>
        ))}
      </div>

      {taskFehler && <p className="text-sm text-red-600">{taskFehler}</p>}

      <div className="rounded border border-gray-200 bg-white p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-medium text-gray-900">
            Task {aktiverTask}: {TASK_TITEL[aktiverTask]}
          </h2>
          <div className="flex gap-2">
            {tasks[aktiverTask - 1].erledigt ? (
              <Button
                variant="secondary" size="sm"
                onClick={() => {
                  const grund = window.prompt('Grund für die Rücksetzung?')
                  if (grund) taskZuruecksetzen.mutate({ taskNr: aktiverTask, grund })
                }}
              >
                Task zurücksetzen
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => taskErledigt.mutate(aktiverTask)}
                disabled={taskErledigt.isPending}
              >
                Task als erledigt markieren
              </Button>
            )}
          </div>
        </div>

        {aktiverTask === 1 && <TerminierungPanel ev={ev} />}
        {aktiverTask === 2 && <TagesordnungPanel ev={ev} />}
        {aktiverTask === 3 && (
          <div className="space-y-8">
            <TeilnehmerPanel ev={ev} />
            <EinladungPanel ev={ev} />
          </div>
        )}
        {aktiverTask === 4 && <DurchfuehrungPanel ev={ev} />}
        {aktiverTask === 5 && <BeschlussfassungPanel ev={ev} />}
      </div>

      <div className="rounded border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-lg font-medium text-gray-900">Verlauf</h2>
        <ul className="space-y-2 text-sm">
          {(ereignisse ?? []).map(e => (
            <li key={e.id} className="flex gap-3">
              <span className="w-40 shrink-0 text-gray-500">{zeit(e.erstellt_am)}</span>
              <span className="w-56 shrink-0 font-medium text-gray-800">{e.typ_display}</span>
              <span className="text-gray-600">
                {e.text}
                {e.alter_wert && e.neuer_wert && (
                  <span className="text-gray-400"> ({e.alter_wert} → {e.neuer_wert})</span>
                )}
                {e.erstellt_von_name && (
                  <span className="text-gray-400"> · {e.erstellt_von_name}</span>
                )}
              </span>
            </li>
          ))}
          {(ereignisse ?? []).length === 0 && (
            <li className="text-gray-500">Kein Eintrag.</li>
          )}
        </ul>
      </div>
    </div>
  )
}
