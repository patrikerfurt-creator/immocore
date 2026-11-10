import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Akte, AktenDokument, Aktenart, aktenApi, RegisterGruppe, Registervorschlag,
} from '../../api/akten'
import { dokumenteApi } from '../../api/dokumente'
import { Button } from '../ui/Button'

/**
 * Gemeinsame Aktenansicht für Haus-, Wohnungs- und Eigentümerakte — links der
 * Registerbaum, rechts die Dokumente. Die drei Akten unterscheiden sich nur in
 * der Auswahl (Objekt/Einheit/Person) und im API-Aufruf; alles ab dem
 * geladenen `akte`-Objekt ist identisch und lebt deshalb hier.
 *
 * Zwei Eigenheiten gegenüber einer gewöhnlichen Dokumentenliste:
 *
 * - LEERE Register bleiben sichtbar. Eine Akte, in der "Versicherungen" fehlt,
 *   weil noch nichts abgelegt wurde, sähe aus wie eine Akte ohne
 *   Versicherungsbedarf. Die leere Zeile zeigt, wo etwas fehlt.
 * - "Ohne Register" steht am Ende und ist die Arbeitsliste: alles, was noch
 *   niemand einsortiert hat — vor allem die importierten Mails.
 */

function datum(wert: string | null): string {
  if (!wert) return '—'
  return new Date(wert).toLocaleDateString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

function fehlertext(fehler: unknown, ersatz: string): string {
  const antwort = (fehler as { response?: { data?: Record<string, unknown> } })?.response?.data
  if (!antwort) return ersatz
  if (typeof antwort.detail === 'string') return antwort.detail
  const erste = Object.values(antwort)[0]
  if (Array.isArray(erste) && typeof erste[0] === 'string') return erste[0]
  return ersatz
}

// ── Registerbaum (links) ───────────────────────────────────────────────────

function RegisterZeile({ gruppe, aktiv, onWaehlen }: {
  gruppe: RegisterGruppe
  aktiv: boolean
  onWaehlen: () => void
}) {
  const leer = gruppe.anzahl === 0
  const sammelgruppe = gruppe.register_id === null

  return (
    <li>
      <button
        type="button"
        onClick={onWaehlen}
        // Einrückung nach Ebene: die Reihenfolge kommt fertig aus dem
        // Backend, hier wird nur die Tiefe sichtbar gemacht.
        style={{ paddingLeft: `${12 + gruppe.ebene * 16}px` }}
        className={`w-full text-left pr-3 py-1.5 border-l-2 flex items-baseline justify-between gap-2 transition-colors ${
          aktiv ? 'bg-blue-50 border-blue-600' : 'border-transparent hover:bg-gray-50'
        }`}
      >
        <span className={`text-sm leading-snug ${leer ? 'text-gray-400' : 'text-gray-900'}`}>
          {gruppe.code && <span className="text-gray-400 mr-1.5">{gruppe.code}</span>}
          {gruppe.bezeichnung}
          {gruppe.objektspezifisch && (
            <span className="ml-1.5 text-[10px] bg-amber-100 text-amber-800 px-1 rounded"
                  title="Nur für dieses Objekt angelegt">
              nur hier
            </span>
          )}
        </span>
        <span className={`text-xs tabular-nums ${
          sammelgruppe && gruppe.anzahl > 0 ? 'text-amber-700 font-medium'
            : leer ? 'text-gray-300' : 'text-gray-500'
        }`}>
          {gruppe.anzahl}
        </span>
      </button>
    </li>
  )
}

// ── Untergliederung anlegen ────────────────────────────────────────────────

function UnterregisterFormular({ objektId, aktenart, eltern, onFertig, onAbbrechen }: {
  objektId: string
  aktenart: Aktenart
  eltern: RegisterGruppe
  onFertig: () => void
  onAbbrechen: () => void
}) {
  const [code, setCode] = useState(`${eltern.code}/A`)
  const [bezeichnung, setBezeichnung] = useState('')
  const [fehler, setFehler] = useState('')

  const mutation = useMutation({
    mutationFn: () => aktenApi.unterregisterAnlegen({
      code,
      bezeichnung,
      aktenart,
      eltern: eltern.register_id!,
      objekt: objektId,
    }),
    onSuccess: onFertig,
    onError: (f) => setFehler(fehlertext(f, 'Das Register konnte nicht angelegt werden.')),
  })

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 flex flex-col gap-2">
      <p className="text-xs text-gray-600">
        Neue Untergliederung unter <strong>{eltern.code} {eltern.bezeichnung}</strong> —
        sie erscheint nur in der Akte dieses Objekts.
      </p>
      <div className="grid grid-cols-3 gap-2">
        <label className="text-xs text-gray-700">
          Kurzzeichen
          <input className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
                 value={code} onChange={e => setCode(e.target.value)} />
        </label>
        <label className="text-xs text-gray-700 col-span-2">
          Bezeichnung
          <input className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
                 value={bezeichnung} onChange={e => setBezeichnung(e.target.value)}
                 placeholder="z. B. Hebeanlage" autoFocus />
        </label>
      </div>
      {fehler && <p className="text-xs text-red-700">{fehler}</p>}
      <div className="flex gap-2">
        <Button onClick={() => mutation.mutate()}
                disabled={!code.trim() || !bezeichnung.trim() || mutation.isPending}>
          {mutation.isPending ? 'Wird angelegt…' : 'Anlegen'}
        </Button>
        <Button variant="secondary" onClick={onAbbrechen}>Abbrechen</Button>
      </div>
    </div>
  )
}

// ── Registervorschlag ───────────────────────────────────────────────────────

const QUELLE_LABEL: Record<Registervorschlag['quelle'], string> = {
  kreditor: 'Standardregister des Kreditors',
  dokumenttyp: 'Regel für den Dokumenttyp',
  ki: 'KI',
  keine: '',
}

/**
 * Der Vorschlag über dem Dropdown. Zwei Fälle:
 *
 * - Ein Register vorgeschlagen -> blaue Zeile mit "Übernehmen". Ein Klick
 *   sortiert ein, ohne die Liste durchsuchen zu müssen.
 * - Kein sicherer Treffer -> grauer Hinweis mit dem Grund, kein Button. Die
 *   Leitlinie ist "vorschlagen, nicht einsortieren": lieber unsortiert als
 *   falsch abgelegt.
 */
function VorschlagHinweis({ vorschlag, uebernehmen, beschaeftigt }: {
  vorschlag: Registervorschlag
  uebernehmen: () => void
  beschaeftigt: boolean
}) {
  if (vorschlag.register_id) {
    return (
      <div className="flex items-start justify-between gap-2 rounded border border-blue-200 bg-blue-50 px-2 py-1.5">
        <div className="text-xs text-blue-900">
          <span className="mr-1">🔮</span>
          Vorschlag: <strong>{vorschlag.code} {vorschlag.bezeichnung}</strong>
          {vorschlag.begruendung && (
            <span className="text-blue-700"> — {vorschlag.begruendung}</span>
          )}
          <span className="mt-0.5 block text-[10px] text-blue-600">
            {QUELLE_LABEL[vorschlag.quelle]}
            {vorschlag.konfidenz !== null &&
              ` · Konfidenz ${Math.round(vorschlag.konfidenz * 100)} %`}
          </span>
        </div>
        <button
          type="button"
          onClick={uebernehmen}
          disabled={beschaeftigt}
          className="shrink-0 rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Übernehmen
        </button>
      </div>
    )
  }

  const grund = vorschlag.fehler || vorschlag.begruendung || 'Kein eindeutiger Treffer.'
  return (
    <p className="rounded border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs text-gray-500">
      <span className="mr-1">🔮</span>Kein sicherer Vorschlag — {grund}
    </p>
  )
}

// ── Dokumentenliste (rechts) ───────────────────────────────────────────────

function DokumentZeile({ dokument, register, aktuellesRegister, aktenart, objektId, onEinsortiert }: {
  dokument: AktenDokument
  register: RegisterGruppe[]
  aktuellesRegister: RegisterGruppe
  aktenart: Aktenart
  objektId?: string
  onEinsortiert: () => void
}) {
  const [offen, setOffen] = useState(false)
  const [fehler, setFehler] = useState('')

  const mutation = useMutation({
    mutationFn: (registerId: string | null) =>
      aktenApi.einsortieren(dokument.id, registerId),
    onSuccess: () => { setOffen(false); onEinsortiert() },
    onError: (f) => setFehler(fehlertext(f, 'Das Einsortieren ist fehlgeschlagen.')),
  })

  // Der Vorschlag wird nur geholt, wenn das Einsortier-Feld offen ist UND das
  // Dokument noch kein Register hat — für ein bereits einsortiertes Dokument
  // ist die aktuelle Zuordnung der bessere Vorgabewert, und die KI-Stufe soll
  // nicht ohne Not Geld kosten. staleTime: der Vorschlag ändert sich während
  // der Sitzung nicht, also kein zweiter Aufruf beim erneuten Öffnen.
  const vorschlagAktiv = offen && !aktuellesRegister.register_id
  const { data: vorschlag, isFetching: vorschlagLaedt } = useQuery({
    queryKey: ['registervorschlag', dokument.id, aktenart, objektId ?? ''],
    queryFn: () => aktenApi.registervorschlag(dokument.id, { aktenart, objektId }),
    enabled: vorschlagAktiv,
    staleTime: Infinity,
  })

  return (
    <li className="py-2 border-b border-gray-100 last:border-0">
      <div className="flex items-baseline justify-between gap-3">
        {/* Angezeigt wird der Anzeigename; der Originaldateiname steht im
            Tooltip — er bleibt der Bezug zur Datei im Archivordner. Kein
            truncate: lange Namen brechen um, statt unlesbar zu enden. */}
        <button
          type="button"
          onClick={() => (dokument.ist_mail
            ? dokumenteApi.openMailVorschau(dokument.id)
            : dokumenteApi.openDatei(dokument.id))}
          className="text-sm text-blue-700 hover:underline text-left break-words"
          title={`${dokument.dateiname}
${dokument.ist_mail ? 'Als Textvorschau öffnen' : 'Öffnen'}`}
        >
          {dokument.ist_mail ? '✉ ' : '📄 '}{dokument.anzeigename}
        </button>
        <span className="text-xs text-gray-400 whitespace-nowrap">
          {datum(dokument.dokument_datum ?? dokument.hochgeladen_am)}
        </span>
      </div>
      <div className="flex items-center gap-3 mt-0.5">
        <span className="text-xs text-gray-500">{dokument.herkunft}</span>
        <button type="button" onClick={() => setOffen(!offen)}
                className="text-xs text-gray-500 hover:text-gray-800 hover:underline">
          {offen ? 'abbrechen' : 'einsortieren'}
        </button>
      </div>

      {offen && (
        <div className="mt-1.5 flex flex-col gap-2">
          {vorschlagAktiv && vorschlagLaedt && (
            <p className="text-xs text-gray-400">Vorschlag wird ermittelt…</p>
          )}
          {vorschlagAktiv && vorschlag && !vorschlagLaedt && (
            <VorschlagHinweis
              vorschlag={vorschlag}
              uebernehmen={() => mutation.mutate(vorschlag.register_id)}
              beschaeftigt={mutation.isPending}
            />
          )}
          <select
            className="border rounded px-2 py-1 text-xs flex-1"
            defaultValue={aktuellesRegister.register_id ?? ''}
            onChange={e => mutation.mutate(e.target.value || null)}
            disabled={mutation.isPending}
          >
            <option value="">— ohne Register —</option>
            {register.filter(r => r.register_id).map(r => (
              <option key={r.register_id} value={r.register_id!}>
                {' '.repeat(r.ebene * 3)}{r.code} {r.bezeichnung}
              </option>
            ))}
          </select>
        </div>
      )}
      {fehler && <p className="text-xs text-red-700 mt-1">{fehler}</p>}
    </li>
  )
}

// ── Aktenansicht ────────────────────────────────────────────────────────────

export default function Aktenansicht({ akte, aktenart, objektId, kontextKey, onReload }: {
  akte: Akte
  aktenart: Aktenart
  /** Objektbezug für Registervorschlag und Untergliederung — fehlt bei der
   *  Eigentümerakte (die keinen einzelnen Objektbezug hat). */
  objektId?: string
  /** Wechselt mit der gewählten Entität (Objekt/Einheit/Person); setzt die
   *  Registerauswahl zurück, wenn man zu einer anderen Akte springt. */
  kontextKey: string
  onReload: () => void
}) {
  const qc = useQueryClient()
  const [gewaehlterCode, setGewaehlterCode] = useState<string | null>(null)
  const [neuesRegister, setNeuesRegister] = useState(false)

  // Beim Wechsel der Entität die Auswahl zurücksetzen — ein Registercode aus
  // der vorigen Akte kann hier ins Leere zeigen.
  useEffect(() => {
    setGewaehlterCode(null)
    setNeuesRegister(false)
  }, [kontextKey])

  const gruppen = akte.register
  const gewaehlt = gruppen.find(g => g.code === gewaehlterCode)
    ?? gruppen.find(g => g.anzahl > 0)
    ?? gruppen[0]

  const neuLaden = () => {
    qc.invalidateQueries({ queryKey: ['registervorschlag'] })
    onReload()
  }

  return (
    <div className="flex-1 min-h-0 flex border border-gray-200 rounded-lg overflow-hidden bg-white">
      {/* Registerbaum */}
      <div className="w-96 shrink-0 border-r border-gray-200 overflow-auto">
        <ul className="py-1">
          {gruppen.map(gruppe => (
            <RegisterZeile
              key={gruppe.code || 'ohne'}
              gruppe={gruppe}
              aktiv={gruppe.code === gewaehlt?.code}
              onWaehlen={() => { setGewaehlterCode(gruppe.code); setNeuesRegister(false) }}
            />
          ))}
        </ul>
      </div>

      {/* Dokumente */}
      <div className="flex-1 min-w-0 flex flex-col">
        {gewaehlt ? (
          <>
            <div className="px-5 py-3 border-b border-gray-200">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-base font-medium text-gray-900">
                    {gewaehlt.code} {gewaehlt.bezeichnung}
                  </h2>
                  {gewaehlt.hinweis && (
                    <p className="text-xs text-gray-500 mt-1 max-w-2xl">
                      {gewaehlt.hinweis}
                    </p>
                  )}
                </div>
                {objektId && gewaehlt.register_id && !gewaehlt.objektspezifisch && (
                  <Button variant="secondary"
                          onClick={() => setNeuesRegister(!neuesRegister)}>
                    Untergliederung
                  </Button>
                )}
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-auto px-5 py-2">
              {neuesRegister && objektId && gewaehlt.register_id && (
                <div className="mb-3">
                  <UnterregisterFormular
                    objektId={objektId}
                    aktenart={aktenart}
                    eltern={gewaehlt}
                    onFertig={() => { setNeuesRegister(false); neuLaden() }}
                    onAbbrechen={() => setNeuesRegister(false)}
                  />
                </div>
              )}

              {gewaehlt.anzahl === 0 ? (
                <p className="text-sm text-gray-400 py-4">
                  Noch nichts abgelegt.
                </p>
              ) : (
                <ul>
                  {gewaehlt.dokumente.map(d => (
                    <DokumentZeile
                      key={d.id}
                      dokument={d}
                      register={gruppen}
                      aktuellesRegister={gewaehlt}
                      aktenart={aktenart}
                      objektId={objektId}
                      onEinsortiert={neuLaden}
                    />
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : (
          <p className="p-5 text-sm text-gray-500">Register links wählen.</p>
        )}
      </div>
    </div>
  )
}
