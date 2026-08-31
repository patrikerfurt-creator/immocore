import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Stepper, StepperStep } from '../../../components/ui/Stepper'
import { objekteApi } from '../../../api/objekte'
import {
  EinzelAbrechnung,
  EinzelAbrechnungPosition,
  KreditorOpZeile,
  jahresabrechnungApi,
} from '../../../api/jahresabrechnung'

// Wizard Jahresabrechnung — HGA-Spec v1.0 Kap. 5 (8 Schritte)

const SCHRITTE = [
  { nr: 1, bezeichnung: 'Jahr & Objekt' },
  { nr: 2, bezeichnung: 'Buchungsprüfung' },
  { nr: 3, bezeichnung: 'Kostenstellen' },
  { nr: 4, bezeichnung: 'Umlageschlüssel' },
  { nr: 5, bezeichnung: 'Rücklagen' },
  { nr: 6, bezeichnung: 'Einzelabrechnungen' },
  { nr: 7, bezeichnung: 'PDF-Vorschau' },
  { nr: 8, bezeichnung: 'Freigabe' },
]

const VS_OPTIONEN = [
  { code: '001', label: '001 — Fläche' },
  { code: '010', label: '010 — MEA' },
  { code: '030', label: '030 — Kopfanteil' },
  { code: '140', label: '140 — Verbrauch Kaltwasser' },
  { code: '141', label: '141 — Verbrauch Warmwasser' },
  { code: '142', label: '142 — Verbrauch Heizung' },
  { code: '143', label: '143 — Verbrauch 143' },
  { code: '144', label: '144 — Verbrauch 144' },
  { code: '145', label: '145 — Verbrauch 145' },
]

function fmt(v: string | number | null | undefined) {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString('de-DE', { minimumFractionDigits: 2 })
}

function apiError(err: unknown): string {
  const e = err as { response?: { data?: { error?: string; detail?: string } } }
  return e.response?.data?.error ?? e.response?.data?.detail ?? 'Unbekannter Fehler'
}

function FehlerBox({ text }: { text: string | null }) {
  if (!text) return null
  return <div className="rounded-md bg-red-50 p-3 text-sm text-red-600">{text}</div>
}

function WarnBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md bg-amber-50 border border-amber-300 p-3 text-sm text-amber-700">
      {children}
    </div>
  )
}

export function JahresabrechnungWizard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const objektId = searchParams.get('objekt') ?? ''
  const jaId = searchParams.get('ja')

  const [schritt, setSchritt] = useState(1)
  const [fehler, setFehler] = useState<string | null>(null)

  const { data: ja } = useQuery({
    queryKey: ['jahresabrechnung', jaId],
    queryFn: () => jahresabrechnungApi.get(jaId!),
    enabled: !!jaId,
  })

  // Beim Öffnen eines bestehenden Entwurfs am Server-Stand fortsetzen
  useEffect(() => {
    if (ja && ja.status === 'entwurf') setSchritt(s => (s === 1 ? ja.current_step : s))
    if (ja && ja.status !== 'entwurf') setSchritt(8)
  }, [ja?.id])  // eslint-disable-line react-hooks/exhaustive-deps

  const gesperrt = ja != null && ja.status !== 'entwurf'

  const weiterMutation = useMutation({
    mutationFn: (ziel: number) => jahresabrechnungApi.schrittSpeichern(jaId!, ziel),
    onSuccess: (_data, ziel) => {
      setFehler(null)
      setSchritt(ziel)
      queryClient.invalidateQueries({ queryKey: ['jahresabrechnung', jaId] })
    },
    onError: err => setFehler(apiError(err)),
  })

  const geheZu = (ziel: number) => {
    if (!jaId) return
    if (gesperrt) { setSchritt(ziel); return }
    weiterMutation.mutate(ziel)
  }

  const stepperSchritte: StepperStep[] = SCHRITTE.map(s => ({
    ...s,
    status:
      s.nr === schritt ? 'aktiv'
      : gesperrt || s.nr < (ja?.current_step ?? 1) ? 'abgeschlossen'
      : 'ausstehend',
  }))

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-800">
            Jahresabrechnung{ja ? ` ${ja.wirtschaftsjahr_jahr} — ${ja.objekt_bezeichnung}` : ''}
          </h1>
          {gesperrt && (
            <p className="text-sm text-green-700 mt-1">
              Freigegeben und gesperrt (unveränderlich).
            </p>
          )}
        </div>
        <button
          onClick={() => navigate('/abrechnung-wp/jahresabrechnung')}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          ← Zur Übersicht
        </button>
      </div>

      <Stepper
        schritte={stepperSchritte}
        onStepClick={jaId ? nr => {
          if (gesperrt || nr <= Math.max(ja?.current_step ?? 1, schritt)) geheZu(nr)
        } : undefined}
      />

      <FehlerBox text={fehler} />

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        {schritt === 1 && (
          <Schritt1JahrObjekt
            objektId={objektId}
            jaId={jaId}
            onAngelegt={neueJa => {
              setSearchParams({ objekt: objektId, ja: neueJa.id })
              setSchritt(Math.max(neueJa.current_step, 2))
            }}
            onFehler={setFehler}
          />
        )}
        {schritt === 2 && jaId && (
          <Schritt2Buchungspruefung
            jaId={jaId} readOnly={gesperrt}
            onWeiter={() => geheZu(3)} onFehler={setFehler}
          />
        )}
        {schritt === 3 && jaId && (
          <Schritt3Kostenstellen jaId={jaId} onWeiter={() => geheZu(4)} onZurueck={() => geheZu(2)} />
        )}
        {schritt === 4 && jaId && (
          <Schritt4Umlageschluessel
            jaId={jaId} readOnly={gesperrt}
            onWeiter={() => geheZu(5)} onZurueck={() => geheZu(3)} onFehler={setFehler}
          />
        )}
        {schritt === 5 && jaId && (
          <Schritt5Ruecklagen jaId={jaId} onWeiter={() => geheZu(6)} onZurueck={() => geheZu(4)} />
        )}
        {schritt === 6 && jaId && (
          <Schritt6Einzelabrechnungen
            jaId={jaId} readOnly={gesperrt}
            onWeiter={() => geheZu(7)} onZurueck={() => geheZu(5)} onFehler={setFehler}
          />
        )}
        {schritt === 7 && jaId && (
          <Schritt7PdfVorschau jaId={jaId} onWeiter={() => geheZu(8)} onZurueck={() => geheZu(6)} />
        )}
        {schritt === 8 && jaId && (
          <Schritt8Freigabe jaId={jaId} gesperrt={gesperrt} onZurueck={() => geheZu(7)} onFehler={setFehler} />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 1 — Jahr & Objekt
// ---------------------------------------------------------------------------

function Schritt1JahrObjekt({ objektId, jaId, onAngelegt, onFehler }: {
  objektId: string
  jaId: string | null
  onAngelegt: (ja: { id: string; current_step: number }) => void
  onFehler: (f: string | null) => void
}) {
  const [wjId, setWjId] = useState('')

  const { data: wirtschaftsjahre = [] } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => objekteApi.wirtschaftsjahre(objektId),
    enabled: !!objektId,
  })

  const { data: schrittDaten } = useQuery({
    queryKey: ['ja-schritt', jaId, 1],
    queryFn: () => jahresabrechnungApi.schritt(jaId!, 1),
    enabled: !!jaId,
  })

  useEffect(() => {
    if (!wjId) {
      const offen = wirtschaftsjahre.find(wj => wj.status === 'offen')
      if (offen) setWjId(offen.id)
    }
  }, [wirtschaftsjahre])  // eslint-disable-line react-hooks/exhaustive-deps

  const anlegen = useMutation({
    mutationFn: () => jahresabrechnungApi.create(objektId, wjId),
    onSuccess: ja => { onFehler(null); onAngelegt(ja) },
    onError: err => onFehler(apiError(err)),
  })

  const wechsel = (schrittDaten?.daten?.eigentuemerwechsel ?? []) as
    Array<{ einheit_nr: string; wechsel_datum: string }>

  return (
    <div className="space-y-4">
      <h2 className="font-semibold text-gray-700">Schritt 1 — Jahr & Objekt</h2>
      {wechsel.length > 0 && (
        <WarnBox>
          Im Wirtschaftsjahr gab es Eigentümerwechsel:{' '}
          {wechsel.map(w => `${w.einheit_nr} (${new Date(w.wechsel_datum).toLocaleDateString('de-DE')})`).join(', ')}.
          Die Abrechnung läuft vollständig auf den aktuellen Eigentümer.
        </WarnBox>
      )}
      <div className="max-w-sm">
        <label className="block text-sm font-medium text-gray-600 mb-1">Wirtschaftsjahr</label>
        <select
          value={wjId}
          onChange={e => setWjId(e.target.value)}
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
        >
          <option value="">— bitte wählen —</option>
          {wirtschaftsjahre.map(wj => (
            <option key={wj.id} value={wj.id} disabled={wj.status !== 'offen'}>
              WJ {wj.jahr} ({wj.status})
            </option>
          ))}
        </select>
        <p className="text-xs text-gray-400 mt-1">Nur offene Wirtschaftsjahre sind wählbar.</p>
      </div>
      <button
        onClick={() => anlegen.mutate()}
        disabled={!wjId || anlegen.isPending}
        className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50"
      >
        {jaId ? 'Fortsetzen →' : 'Jahresabrechnung anlegen →'}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 2 — Buchungsprüfung
// ---------------------------------------------------------------------------

function Schritt2Buchungspruefung({ jaId, readOnly, onWeiter, onFehler }: {
  jaId: string; readOnly: boolean; onWeiter: () => void; onFehler: (t: string) => void
}) {
  const queryClient = useQueryClient()
  const [gewaehlt, setGewaehlt] = useState<number[]>([])
  const [erfolg, setErfolg] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['ja-schritt', jaId, 2],
    queryFn: () => jahresabrechnungApi.schritt(jaId, 2),
  })

  const vortrag = useMutation({
    mutationFn: () => jahresabrechnungApi.kreditorVortrag(jaId, gewaehlt),
    onSuccess: res => {
      const ohneBuchung = res.ops.filter(o => !o.gebucht).length
      setErfolg(
        `${res.anzahl} offene(r) Posten über ${fmt(res.summe)} € nach ${res.vorgetragen_nach} ` +
        `vorgetragen (${res.anzahl_gebucht} mit Buchung` +
        (ohneBuchung > 0 ? `, ${ohneBuchung} ohne Buchung` : '') + ').'
      )
      setGewaehlt([])
      onFehler('')
      queryClient.invalidateQueries({ queryKey: ['ja-schritt', jaId, 2] })
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      onFehler(msg ?? 'Saldovortrag fehlgeschlagen.')
    },
  })

  if (isLoading) return <p className="text-sm text-gray-400">Lade...</p>

  const daten = (data?.daten ?? {}) as {
    blockiert?: boolean
    folgejahr?: number
    kreditor_ops?: KreditorOpZeile[]
    vorgetragene_ops?: KreditorOpZeile[]
    wkz_ops?: Array<{ vorlage: string; faellig_am: string; status: string }>
  }
  const offene = daten.kreditor_ops ?? []
  const vorgetragene = daten.vorgetragene_ops ?? []
  const folgejahr = daten.folgejahr
  const alleGewaehlt = offene.length > 0 && gewaehlt.length === offene.length
  const summeGewaehlt = offene
    .filter(op => gewaehlt.includes(op.op_nummer))
    .reduce((s, op) => s + Number(op.betrag_offen), 0)

  const umschalten = (nr: number) =>
    setGewaehlt(v => (v.includes(nr) ? v.filter(x => x !== nr) : [...v, nr]))

  return (
    <div className="space-y-4">
      <h2 className="font-semibold text-gray-700">Schritt 2 — Buchungsprüfung</h2>

      {daten.blockiert ? (
        <div className="rounded-md bg-red-50 border border-red-300 p-3 text-sm text-red-700">
          Es existieren offene Kreditoren-OPs mit Fälligkeit im Wirtschaftsjahr —
          Weiterschalten gesperrt. Entweder in der{' '}
          <a href="/buchhaltung/kreditoren" className="underline">Kreditoren-OP-Liste</a> klären
          oder unten auswählen und per Saldovortrag nach {folgejahr} übertragen.
        </div>
      ) : (
        <p className="text-sm text-green-700">✓ Keine offenen Kreditoren-OPs im Wirtschaftsjahr.</p>
      )}

      {erfolg && (
        <div className="rounded-md bg-green-50 border border-green-300 p-3 text-sm text-green-800">
          {erfolg}
        </div>
      )}

      {offene.length > 0 && (
        <div className="space-y-3">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 w-8">
                  {!readOnly && (
                    <input
                      type="checkbox"
                      checked={alleGewaehlt}
                      onChange={() =>
                        setGewaehlt(alleGewaehlt ? [] : offene.map(op => op.op_nummer))}
                      aria-label="Alle offenen Posten auswählen"
                    />
                  )}
                </th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">OP-Nr</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Kreditor</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Offen</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Fällig</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {offene.map(op => (
                <tr key={op.op_nummer} className={gewaehlt.includes(op.op_nummer) ? 'bg-primary-50' : ''}>
                  <td className="px-3 py-2">
                    {!readOnly && (
                      <input
                        type="checkbox"
                        checked={gewaehlt.includes(op.op_nummer)}
                        onChange={() => umschalten(op.op_nummer)}
                        aria-label={`OP-${op.op_nummer} auswählen`}
                      />
                    )}
                  </td>
                  <td className="px-3 py-2">{op.op_nummer}</td>
                  <td className="px-3 py-2">
                    {op.kreditor}
                    {!op.buchung_festgeschrieben && (
                      <span
                        className="ml-2 text-xs text-amber-700"
                        title="Zu diesem OP gibt es im Wirtschaftsjahr keine festgeschriebene
                               Buchung — der Vortrag verschiebt nur den offenen Posten."
                      >
                        (ohne festgeschriebene Buchung)
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">{fmt(op.betrag_offen)} €</td>
                  <td className="px-3 py-2">{new Date(op.faellig_ab).toLocaleDateString('de-DE')}</td>
                  <td className="px-3 py-2">{op.status}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {!readOnly && (
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2">
              <p className="text-xs text-gray-600">
                Saldovortrag nach {folgejahr}: Die Kreditorenverbindlichkeit wird zum
                Jahresende aufgelöst und zum {folgejahr}-Beginn wieder eingestellt
                (Kreditorkonto gegen Schwebekonto, erfolgsneutral). Der offene Posten
                bleibt offen und zahlbar — die Kosten fallen nach dem Abflussprinzip
                erst im Jahr der Zahlung an.
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => { setErfolg(null); vortrag.mutate() }}
                  disabled={gewaehlt.length === 0 || vortrag.isPending}
                  className="px-4 py-2 bg-amber-600 text-white text-sm rounded hover:bg-amber-700 disabled:opacity-50"
                >
                  {vortrag.isPending
                    ? 'Buche...'
                    : `Saldovortrag nach ${folgejahr} buchen`}
                </button>
                <span className="text-sm text-gray-600">
                  {gewaehlt.length === 0
                    ? 'Keine Posten ausgewählt.'
                    : `${gewaehlt.length} Posten, ${fmt(summeGewaehlt)} €`}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {vorgetragene.length > 0 && (
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-gray-600">
            Ins Folgejahr vorgetragen (blockiert nicht mehr)
          </h3>
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-600">OP-Nr</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Kreditor</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Offen</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Fällig</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Vorgetragen nach</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {vorgetragene.map(op => (
                <tr key={op.op_nummer} className="text-gray-500">
                  <td className="px-3 py-2">{op.op_nummer}</td>
                  <td className="px-3 py-2">{op.kreditor}</td>
                  <td className="px-3 py-2 text-right">{fmt(op.betrag_offen)} €</td>
                  <td className="px-3 py-2">{new Date(op.faellig_ab).toLocaleDateString('de-DE')}</td>
                  <td className="px-3 py-2">{op.vorgetragen_nach}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(daten.wkz_ops?.length ?? 0) > 0 && (
        <WarnBox>
          {daten.wkz_ops!.length} offene wiederkehrende Buchung(en) im WJ (kein Blocker).
        </WarnBox>
      )}

      {!readOnly && (
        <button
          onClick={onWeiter}
          disabled={daten.blockiert}
          className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50"
        >
          Weiter →
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 3 — Kostenstellen
// ---------------------------------------------------------------------------

function Schritt3Kostenstellen({ jaId, onWeiter, onZurueck }: {
  jaId: string; onWeiter: () => void; onZurueck: () => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['ja-kostenstellen', jaId],
    queryFn: () => jahresabrechnungApi.kostenstellen(jaId),
  })

  if (isLoading) return <p className="text-sm text-gray-400">Lade...</p>

  return (
    <div className="space-y-4">
      <h2 className="font-semibold text-gray-700">Schritt 3 — Kostenstellen-Übersicht</h2>
      {data && !data.wirtschaftsplan_vorhanden && (
        <WarnBox>
          Kein beschlossener Wirtschaftsplan für dieses WJ — es werden nur Ist-Kosten
          ohne Vergleichsspalte angezeigt.
        </WarnBox>
      )}
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-3 py-2 text-left font-medium text-gray-600">Konto</th>
            <th className="px-3 py-2 text-left font-medium text-gray-600">Bezeichnung</th>
            <th className="px-3 py-2 text-right font-medium text-gray-600">Ist</th>
            <th className="px-3 py-2 text-right font-medium text-gray-600">Plan</th>
            <th className="px-3 py-2 text-right font-medium text-gray-600">Abweichung</th>
            <th className="px-3 py-2 text-right font-medium text-gray-600">%</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data?.positionen.map(p => (
            <tr key={p.konto_id}>
              <td className="px-3 py-2 font-mono">{p.kontonummer}</td>
              <td className="px-3 py-2">{p.kontoname}</td>
              <td className="px-3 py-2 text-right">{fmt(p.ist)} €</td>
              <td className="px-3 py-2 text-right">{p.plan != null ? `${fmt(p.plan)} €` : '—'}</td>
              <td className="px-3 py-2 text-right">{p.abweichung != null ? `${fmt(p.abweichung)} €` : '—'}</td>
              <td className="px-3 py-2 text-right">{p.abweichung_prozent != null ? `${fmt(p.abweichung_prozent)} %` : '—'}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t-2 border-gray-300 font-semibold">
          <tr>
            <td className="px-3 py-2" colSpan={2}>Summe</td>
            <td className="px-3 py-2 text-right">{fmt(data?.summe_ist ?? 0)} €</td>
            <td className="px-3 py-2 text-right">{data?.summe_plan != null ? `${fmt(data.summe_plan)} €` : '—'}</td>
            <td colSpan={2} />
          </tr>
        </tfoot>
      </table>
      <div className="flex gap-2">
        <button onClick={onZurueck} className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50">← Zurück</button>
        <button onClick={onWeiter} className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700">Weiter →</button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 4 — Umlageschlüssel
// ---------------------------------------------------------------------------

function Schritt4Umlageschluessel({ jaId, readOnly, onWeiter, onZurueck, onFehler }: {
  jaId: string; readOnly: boolean
  onWeiter: () => void; onZurueck: () => void; onFehler: (f: string | null) => void
}) {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['ja-umlageschluessel', jaId],
    queryFn: () => jahresabrechnungApi.umlageschluessel(jaId),
  })

  const korrektur = useMutation({
    mutationFn: ({ kontoId, vsCode }: { kontoId: string; vsCode: string }) =>
      jahresabrechnungApi.umlageschluesselKorrigieren(jaId, kontoId, vsCode),
    onSuccess: neu => {
      onFehler(null)
      queryClient.setQueryData(['ja-umlageschluessel', jaId], neu)
      queryClient.invalidateQueries({ queryKey: ['ja-kostenstellen', jaId] })
    },
    onError: err => onFehler(apiError(err)),
  })

  const neuEinlesen = useMutation({
    mutationFn: () => jahresabrechnungApi.umlageschluesselNeuEinlesen(jaId),
    onSuccess: res => {
      onFehler(null)
      queryClient.invalidateQueries({ queryKey: ['ja-umlageschluessel', jaId] })
      queryClient.invalidateQueries({ queryKey: ['ja-kostenstellen', jaId] })
      window.alert(`VS neu eingelesen: ${res.zugeordnet} von ${res.konten_gesamt} Konten zugeordnet.`)
    },
    onError: err => onFehler(apiError(err)),
  })

  if (isLoading) return <p className="text-sm text-gray-400">Lade...</p>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-700">Schritt 4 — Umlageschlüssel je Konto</h2>
        {!readOnly && (
          <button
            onClick={() => {
              if (window.confirm('VS-Zuordnungen für dieses Wirtschaftsjahr neu aus dem Kontenrahmen laden? Manuelle Korrekturen werden dabei überschrieben.'))
                neuEinlesen.mutate()
            }}
            className="px-3 py-1.5 border border-primary-300 text-primary-700 text-sm rounded hover:bg-primary-50"
          >
            ↻ VS neu einlesen
          </button>
        )}
      </div>
      <p className="text-sm text-gray-500">
        Korrekturen gelten nur für das aktuelle Wirtschaftsjahr, nicht rückwirkend.
        „VS neu einlesen" setzt die Zuordnung aller Konten auf den Kontenrahmen (Konto-Feld) zurück.
      </p>
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-3 py-2 text-left font-medium text-gray-600">Konto</th>
            <th className="px-3 py-2 text-left font-medium text-gray-600">Bezeichnung</th>
            <th className="px-3 py-2 text-left font-medium text-gray-600">Verteilerschlüssel</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data?.konten.map(k => (
            <tr key={k.konto_id}>
              <td className="px-3 py-2 font-mono">{k.kontonummer}</td>
              <td className="px-3 py-2">{k.kontoname}</td>
              <td className="px-3 py-2">
                {readOnly ? (
                  <span>{k.vs_code ?? '—'}</span>
                ) : (
                  <select
                    value={k.vs_code ?? ''}
                    onChange={e => korrektur.mutate({ kontoId: k.konto_id, vsCode: e.target.value })}
                    className="border border-gray-300 rounded px-2 py-1 text-sm"
                  >
                    {k.vs_code == null && <option value="">— kein VS —</option>}
                    {(data?.vs_optionen ?? VS_OPTIONEN).map(o => (
                      <option key={o.code} value={o.code}>{o.label}</option>
                    ))}
                  </select>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex gap-2">
        <button onClick={onZurueck} className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50">← Zurück</button>
        {!readOnly && (
          <button onClick={onWeiter} className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700">Weiter →</button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 5 — Rücklagen
// ---------------------------------------------------------------------------

function Schritt5Ruecklagen({ jaId, onWeiter, onZurueck }: {
  jaId: string; onWeiter: () => void; onZurueck: () => void
}) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['ja-ruecklagen', jaId],
    queryFn: () => jahresabrechnungApi.ruecklagen(jaId),
  })
  const planMutation = useMutation({
    mutationFn: ({ baNr, betrag }: { baNr: string; betrag: string | null }) =>
      jahresabrechnungApi.ruecklagenPlanSpeichern(jaId, baNr, betrag),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ja-ruecklagen', jaId] }),
  })

  if (isLoading) return <p className="text-sm text-gray-400">Lade...</p>

  const speichern = (baNr: string, raw: string) => {
    const wert = raw.trim().replace(/\./g, '').replace(',', '.')
    planMutation.mutate({ baNr, betrag: wert === '' ? null : wert })
  }

  return (
    <div className="space-y-4">
      <h2 className="font-semibold text-gray-700">Schritt 5 — Rücklagen</h2>
      {(data?.klaerungsfaelle ?? 0) > 0 && (
        <div className="rounded-md bg-amber-50 border border-amber-300 p-3 text-sm text-amber-800">
          Hinweis: Bei {data!.klaerungsfaelle} Rücklage(n) weicht der berechnete Endbestand vom
          Bankauszug ab (Klärungsfall). Dies sperrt den Wizard nicht.
        </div>
      )}
      {data?.ruecklagen.length === 0 && (
        <p className="text-sm text-gray-400">Keine Rücklagen-Bankkonten am Objekt.</p>
      )}
      {(data?.ruecklagen.length ?? 0) > 0 && (
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-600">Rücklage</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Anfangsbestand</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Zuführung (Ist)</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Zuführung lt. Wirtschaftsplan</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Entnahmen</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Endbestand (ber.)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {data!.ruecklagen.map(r => (
              <tr key={r.bankkonto_id}>
                <td className="px-3 py-2">{r.bezeichnung} <span className="text-xs text-gray-400">(BA {r.ba_nr})</span></td>
                <td className="px-3 py-2 text-right">{fmt(r.anfangsbestand)} €</td>
                <td className="px-3 py-2 text-right">{fmt(r.zufuehrungen)} €</td>
                <td className="px-3 py-2 text-right">
                  <input
                    type="text"
                    defaultValue={r.zufuehrung_plan ? fmt(r.zufuehrung_plan) : ''}
                    placeholder="lt. Plan"
                    onBlur={e => speichern(r.ba_nr, e.target.value)}
                    className="w-28 text-right border border-gray-300 rounded px-2 py-1"
                  />
                </td>
                <td className="px-3 py-2 text-right">{fmt(r.entnahmen)} €</td>
                <td className="px-3 py-2 text-right">{fmt(r.endbestand_berechnet)} €</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-gray-500">
        „Zuführung lt. Wirtschaftsplan" ist der fixe Objekt-Gesamtbetrag, der in der Abrechnung
        ausgewiesen wird. Leer lassen = Summe der Sollstellungen verwenden.
      </p>
      <div className="flex gap-2">
        <button onClick={onZurueck} className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50">← Zurück</button>
        <button
          onClick={onWeiter}
          className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700"
        >
          Weiter →
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 6 — Einzelabrechnungen
// ---------------------------------------------------------------------------

function Schritt6Einzelabrechnungen({ jaId, readOnly, onWeiter, onZurueck, onFehler }: {
  jaId: string; readOnly: boolean
  onWeiter: () => void; onZurueck: () => void; onFehler: (f: string | null) => void
}) {
  const queryClient = useQueryClient()
  const [offenEinheit, setOffenEinheit] = useState<string | null>(null)

  const { data: eas = [], isLoading } = useQuery({
    queryKey: ['ja-einzelabrechnungen', jaId],
    queryFn: () => jahresabrechnungApi.einzelabrechnungen(jaId),
  })

  const berechnen = useMutation({
    mutationFn: () => jahresabrechnungApi.einzelabrechnungenBerechnen(jaId),
    onSuccess: neu => {
      onFehler(null)
      queryClient.setQueryData(['ja-einzelabrechnungen', jaId], neu)
    },
    onError: err => onFehler(apiError(err)),
  })

  const hatFehler = eas.some(ea => ea.positionen.some(p => p.fehler))

  if (isLoading) return <p className="text-sm text-gray-400">Lade...</p>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-700">Schritt 6 — Einzelabrechnungen</h2>
        {!readOnly && (
          <button
            onClick={() => berechnen.mutate()}
            disabled={berechnen.isPending}
            className="px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50"
          >
            {eas.length ? 'Neu berechnen' : 'Berechnen'}
          </button>
        )}
      </div>

      {hatFehler && (
        <div className="rounded-md bg-red-50 border border-red-300 p-3 text-sm text-red-700">
          Verteilerschlüssel-Fehler in einzelnen Positionen — Verbrauchswerte
          unvollständig. Bitte VS-Import nachholen oder manuell erfassen;
          Freigabe ist bis zur Klärung gesperrt.
        </div>
      )}

      {eas.length === 0 ? (
        <p className="text-sm text-gray-400">Noch nicht berechnet.</p>
      ) : (
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-600">Einheit</th>
              <th className="px-3 py-2 text-left font-medium text-gray-600">Eigentümer</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Kostenanteil</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Hausgeld-Soll</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Ergebnis</th>
              <th className="px-3 py-2 text-left font-medium text-gray-600"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {eas.map(ea => (
              <EinzelabrechnungZeile
                key={ea.id}
                jaId={jaId}
                ea={ea}
                readOnly={readOnly}
                offen={offenEinheit === ea.einheit}
                onToggle={() => setOffenEinheit(offenEinheit === ea.einheit ? null : ea.einheit)}
                onFehler={onFehler}
              />
            ))}
          </tbody>
        </table>
      )}

      <div className="flex gap-2">
        <button onClick={onZurueck} className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50">← Zurück</button>
        {!readOnly && (
          <button
            onClick={onWeiter}
            disabled={eas.length === 0}
            className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50"
          >
            Weiter →
          </button>
        )}
      </div>
    </div>
  )
}

function EinzelabrechnungZeile({ jaId, ea, readOnly, offen, onToggle, onFehler }: {
  jaId: string; ea: EinzelAbrechnung; readOnly: boolean
  offen: boolean; onToggle: () => void; onFehler: (f: string | null) => void
}) {
  const queryClient = useQueryClient()
  const [positionen, setPositionen] = useState<EinzelAbrechnungPosition[]>(ea.positionen)
  const [grund, setGrund] = useState('')

  useEffect(() => { setPositionen(ea.positionen) }, [ea.positionen])

  const korrektur = useMutation({
    mutationFn: () => jahresabrechnungApi.einzelabrechnungKorrigieren(jaId, ea.einheit, positionen, grund),
    onSuccess: () => {
      onFehler(null)
      setGrund('')
      queryClient.invalidateQueries({ queryKey: ['ja-einzelabrechnungen', jaId] })
    },
    onError: err => onFehler(apiError(err)),
  })

  const ergebnis = Number(ea.abrechnungsergebnis)
  const hatFehler = ea.positionen.some(p => p.fehler)

  return (
    <>
      <tr className={`hover:bg-gray-50 cursor-pointer ${hatFehler ? 'bg-red-50' : ''}`} onClick={onToggle}>
        <td className="px-3 py-2 font-medium">
          {ea.einheit_nr}
          {ea.hinweis_eigentuemerwechsel && (
            <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">Wechsel</span>
          )}
          {hatFehler && (
            <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-800">VS-Fehler</span>
          )}
        </td>
        <td className="px-3 py-2">{ea.eigentuemer_name}</td>
        <td className="px-3 py-2 text-right">{fmt(ea.kostenanteil_gesamt)} €</td>
        <td className="px-3 py-2 text-right">{fmt(ea.hausgeld_soll_gesamt)} €</td>
        <td className={`px-3 py-2 text-right font-semibold ${ergebnis > 0 ? 'text-red-600' : ergebnis < 0 ? 'text-green-600' : ''}`}>
          {fmt(ea.abrechnungsergebnis)} €
          <span className="ml-1 text-xs font-normal text-gray-400">
            {ergebnis > 0 ? 'Nachz.' : ergebnis < 0 ? 'Guth.' : ''}
          </span>
        </td>
        <td className="px-3 py-2 text-gray-400 text-xs">{offen ? '▲' : '▼'}</td>
      </tr>
      {offen && (
        <tr>
          <td colSpan={6} className="px-3 py-3 bg-gray-50">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="text-gray-500">
                  <th className="px-2 py-1 text-left">Konto</th>
                  <th className="px-2 py-1 text-left">Bezeichnung</th>
                  <th className="px-2 py-1 text-left">VS</th>
                  <th className="px-2 py-1 text-right">Gesamtkosten</th>
                  <th className="px-2 py-1 text-right">Anteil</th>
                  <th className="px-2 py-1 text-right">Betrag</th>
                </tr>
              </thead>
              <tbody>
                {positionen.map((p, idx) => (
                  <tr key={`${p.kontonummer}-${idx}`} className={p.fehler ? 'text-red-600' : ''}>
                    <td className="px-2 py-1 font-mono">{p.kontonummer}</td>
                    <td className="px-2 py-1">
                      {p.kontoname}
                      {p.fehler && <span className="block text-red-500">{p.fehler}</span>}
                      {p.manuell_korrigiert && <span className="block text-amber-600">manuell korrigiert</span>}
                    </td>
                    <td className="px-2 py-1 font-mono">{p.vs_code ?? '—'}</td>
                    <td className="px-2 py-1 text-right">{fmt(p.gesamtkosten)} €</td>
                    <td className="px-2 py-1 text-right">{p.anteil ?? '—'}</td>
                    <td className="px-2 py-1 text-right">
                      {readOnly || p.fehler ? (
                        p.betrag != null ? `${fmt(p.betrag)} €` : '—'
                      ) : (
                        <input
                          value={p.betrag ?? ''}
                          onChange={e => {
                            const kopie = [...positionen]
                            kopie[idx] = { ...p, betrag: e.target.value, manuell_korrigiert: true }
                            setPositionen(kopie)
                          }}
                          onClick={e => e.stopPropagation()}
                          className="w-24 border border-gray-300 rounded px-1 py-0.5 text-right"
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!readOnly && (
              <div className="flex items-center gap-2 mt-3" onClick={e => e.stopPropagation()}>
                <input
                  placeholder="Korrekturgrund (Pflicht)"
                  value={grund}
                  onChange={e => setGrund(e.target.value)}
                  className="flex-1 border border-gray-300 rounded px-2 py-1 text-xs"
                />
                <button
                  onClick={() => korrektur.mutate()}
                  disabled={!grund.trim() || korrektur.isPending}
                  className="px-3 py-1 bg-primary-600 text-white text-xs rounded hover:bg-primary-700 disabled:opacity-50"
                >
                  Korrektur speichern
                </button>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Schritt 7 — PDF-Vorschau
// ---------------------------------------------------------------------------

function Schritt7PdfVorschau({ jaId, onWeiter, onZurueck }: {
  jaId: string; onWeiter: () => void; onZurueck: () => void
}) {
  const { data: eas = [], isLoading } = useQuery({
    queryKey: ['ja-einzelabrechnungen', jaId],
    queryFn: () => jahresabrechnungApi.einzelabrechnungen(jaId),
  })

  const oeffnePdf = async (einheitId: string) => {
    const blob = await jahresabrechnungApi.pdfVorschau(jaId, einheitId)
    const url = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }))
    window.open(url, '_blank')
  }

  if (isLoading) return <p className="text-sm text-gray-400">Lade...</p>

  return (
    <div className="space-y-4">
      <h2 className="font-semibold text-gray-700">Schritt 7 — PDF-Vorschau</h2>
      <p className="text-sm text-gray-500">
        Vorschau-Rendering — die PDFs werden erst bei der Freigabe (Schritt 8) final
        erzeugt und als Dokument abgelegt.
      </p>
      <ul className="divide-y divide-gray-100 border border-gray-200 rounded-lg bg-white">
        {eas.map(ea => (
          <li key={ea.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
            <span>
              {ea.einheit_nr} — {ea.eigentuemer_name}
              {ea.hinweis_eigentuemerwechsel && (
                <span className="ml-2 text-xs text-amber-600">(Fußnote Eigentümerwechsel)</span>
              )}
            </span>
            <button
              onClick={() => oeffnePdf(ea.einheit)}
              className="px-3 py-1 border border-gray-300 text-xs rounded hover:bg-gray-50"
            >
              PDF ansehen
            </button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <button onClick={onZurueck} className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50">← Zurück zu Schritt 6</button>
        <button onClick={onWeiter} className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700">Weiter →</button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 8 — Freigabe
// ---------------------------------------------------------------------------

function Schritt8Freigabe({ jaId, gesperrt, onZurueck, onFehler }: {
  jaId: string; gesperrt: boolean; onZurueck: () => void; onFehler: (f: string | null) => void
}) {
  const queryClient = useQueryClient()
  const [hinweis, setHinweis] = useState<string | null>(null)

  const { data: eas = [] } = useQuery({
    queryKey: ['ja-einzelabrechnungen', jaId],
    queryFn: () => jahresabrechnungApi.einzelabrechnungen(jaId),
  })

  const freigeben = useMutation({
    mutationFn: () => jahresabrechnungApi.freigeben(jaId),
    onSuccess: resp => {
      onFehler(null)
      setHinweis(resp.hinweis)
      queryClient.invalidateQueries({ queryKey: ['jahresabrechnung', jaId] })
      queryClient.invalidateQueries({ queryKey: ['ja-einzelabrechnungen', jaId] })
    },
    onError: err => onFehler(apiError(err)),
  })

  const nachzahlungen = eas.filter(ea => Number(ea.abrechnungsergebnis) > 0).length
  const guthaben = eas.filter(ea => Number(ea.abrechnungsergebnis) < 0).length

  return (
    <div className="space-y-4">
      <h2 className="font-semibold text-gray-700">Schritt 8 — Freigabe & Buchung</h2>

      {hinweis && (
        <div className="rounded-md bg-green-50 border border-green-300 p-3 text-sm text-green-800 whitespace-pre-line">
          ✓ {hinweis}
        </div>
      )}

      {gesperrt && !hinweis ? (
        <p className="text-sm text-green-700">
          Diese Jahresabrechnung ist freigegeben und gesperrt (unveränderlich).
        </p>
      ) : !hinweis && (
        <>
          <div className="rounded-md bg-gray-50 border border-gray-200 p-4 text-sm space-y-1">
            <p>{eas.length} Einzelabrechnung(en) — {nachzahlungen} Nachzahlung(en), {guthaben} Guthaben.</p>
            <p className="text-gray-500">
              Die Freigabe sperrt die Abrechnung unveränderlich, erzeugt die finalen PDFs
              und stellt die Abrechnungsergebnisse im Hausgeld-Nebenbuch ins Soll
              (keine Sachkontenbuchung). Ein Auszahlungslauf für Guthaben wird{' '}
              <strong>nicht</strong> automatisch gestartet.
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={onZurueck} className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50">← Zurück</button>
            <button
              onClick={() => freigeben.mutate()}
              disabled={freigeben.isPending || eas.length === 0}
              className="px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:opacity-50"
            >
              {freigeben.isPending ? 'Freigabe läuft…' : 'Jetzt freigeben & sperren'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
