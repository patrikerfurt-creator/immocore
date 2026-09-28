import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AktenDokument, aktenApi, RegisterGruppe } from '../../api/akten'
import { dokumenteApi } from '../../api/dokumente'
import { objekteApi } from '../../api/objekte'
import { Button } from '../../components/ui/Button'

/**
 * Hausakte eines Objekts — links der Registerbaum, rechts die Dokumente.
 *
 * Zwei Eigenheiten gegenüber einer gewöhnlichen Dokumentenliste:
 *
 * - LEERE Register bleiben sichtbar. Eine Akte, in der "Versicherungen"
 *   fehlt, weil noch nichts abgelegt wurde, sähe aus wie eine Akte ohne
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

function UnterregisterFormular({ objektId, eltern, onFertig, onAbbrechen }: {
  objektId: string
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
      aktenart: 'haus',
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

// ── Dokumentenliste (rechts) ───────────────────────────────────────────────

function DokumentZeile({ dokument, register, aktuellesRegister, onEinsortiert }: {
  dokument: AktenDokument
  register: RegisterGruppe[]
  aktuellesRegister: RegisterGruppe
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
        <div className="mt-1.5 flex items-center gap-2">
          <select
            className="border rounded px-2 py-1 text-xs flex-1"
            defaultValue={aktuellesRegister.register_id ?? ''}
            onChange={e => mutation.mutate(e.target.value || null)}
            disabled={mutation.isPending}
          >
            <option value="">— ohne Register —</option>
            {register.filter(r => r.register_id).map(r => (
              <option key={r.register_id} value={r.register_id!}>
                {' '.repeat(r.ebene * 3)}{r.code} {r.bezeichnung}
              </option>
            ))}
          </select>
        </div>
      )}
      {fehler && <p className="text-xs text-red-700 mt-1">{fehler}</p>}
    </li>
  )
}

// ── Seite ──────────────────────────────────────────────────────────────────

export default function Hausakte() {
  const qc = useQueryClient()
  const [suchParams, setSuchParams] = useSearchParams()
  const objektId = suchParams.get('objekt') ?? ''
  const [gewaehlterCode, setGewaehlterCode] = useState<string | null>(null)
  const [neuesRegister, setNeuesRegister] = useState(false)

  const { data: objekte = [] } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
  })

  const { data: akte, isLoading, isError } = useQuery({
    queryKey: ['hausakte', objektId],
    queryFn: () => aktenApi.hausakte(objektId),
    enabled: Boolean(objektId),
  })

  // Beim Objektwechsel die Auswahl zurücksetzen — ein Registercode aus dem
  // vorigen Objekt kann hier ins Leere zeigen.
  useEffect(() => {
    setGewaehlterCode(null)
    setNeuesRegister(false)
  }, [objektId])

  const gruppen = akte?.register ?? []
  const gewaehlt = gruppen.find(g => g.code === gewaehlterCode)
    ?? gruppen.find(g => g.anzahl > 0)
    ?? gruppen[0]

  const neuLaden = () => qc.invalidateQueries({ queryKey: ['hausakte', objektId] })

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] min-h-[32rem]">
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold text-gray-900">Hausakte</h1>
          {akte && (
            <span className="text-sm text-gray-500">
              {akte.anzahl_dokumente} Dokument{akte.anzahl_dokumente === 1 ? '' : 'e'}
            </span>
          )}
        </div>
        <select
          className="border rounded px-2 py-1 text-sm min-w-72"
          value={objektId}
          onChange={e => setSuchParams(e.target.value ? { objekt: e.target.value } : {})}
        >
          <option value="">Objekt wählen…</option>
          {objekte.map(o => (
            <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
          ))}
        </select>
      </div>

      {!objektId && (
        <div className="flex-1 flex items-center justify-center border border-gray-200 rounded-lg bg-white">
          <p className="text-sm text-gray-500">
            Bitte oben rechts ein Objekt wählen.
          </p>
        </div>
      )}

      {objektId && isLoading && (
        <p className="text-sm text-gray-500">Akte wird geladen…</p>
      )}
      {objektId && isError && (
        <p className="text-sm text-red-700">Die Akte konnte nicht geladen werden.</p>
      )}

      {akte && (
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
                    {gewaehlt.register_id && !gewaehlt.objektspezifisch && (
                      <Button variant="secondary"
                              onClick={() => setNeuesRegister(!neuesRegister)}>
                        Untergliederung
                      </Button>
                    )}
                  </div>
                </div>

                <div className="flex-1 min-h-0 overflow-auto px-5 py-2">
                  {neuesRegister && gewaehlt.register_id && (
                    <div className="mb-3">
                      <UnterregisterFormular
                        objektId={objektId}
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
      )}
    </div>
  )
}
