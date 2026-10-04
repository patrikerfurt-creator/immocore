import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { korrespondenzFehlerText, serienlaeufeApi, druckstapelApi, vorlagenApi } from '../../../api/korrespondenz'
import { mitarbeiterApi } from '../../../api/mitarbeiter'
import { objekteApi } from '../../../api/objekte'
import { Button } from '../../../components/ui/Button'
import { Stepper, type StepperStep } from '../../../components/ui/Stepper'
import { useObjektStore } from '../../../stores/objekt'
import type { Eingabefeld, Serienlauf, Vorlage } from '../../../types'
import { eingabewerteAufbereiten } from '../editor/PdfVorschauPanel'
import { ANLASS_LABEL, KANAL_LABEL } from '../konstanten'
import { EingabefelderFormular } from '../schreiben/EingabefelderFormular'
import { PdfAnzeige } from '../schreiben/PdfAnzeige'
import { fehlendePflichtfelder, istMahnAnlass, type EingabeWerte } from '../schreiben/schreibenKonstanten'
import { EmpfaengerkreisSchritt } from './EmpfaengerkreisSchritt'
import { LEERE_AUSWAHL, filterAufbauen, filterBeschreibung, type EmpfaengerAuswahl } from './empfaengerFilter'
import { SerienbriefVorschau } from './SerienbriefVorschau'

const SCHRITTE = ['Vorlage', 'Empfänger', 'Angaben', 'Vorschau', 'Freigabe']
const POLL_MS = 3000

/** Vorlagen, die als Serienbrief taugen: aktiv, freigegebene Version, kein Mahn-/Vorgangsbezug. */
export function serienbriefVorlagen(vorlagen: Vorlage[]): Vorlage[] {
  return vorlagen.filter(v => v.aktiv && !!v.aktive_version && !istMahnAnlass(v.anlass) && v.anlass !== 'vorgang_antwort')
}

/** Serienbrief-Assistent (Spec 7.4): Vorlage → Empfängerkreis → Angaben → Vorschau → Freigabe. */
export function SerienbriefAssistentPage() {
  const qc = useQueryClient()
  const { selectedId } = useObjektStore()
  const [schritt, setSchritt] = useState(1)
  const [vorlageId, setVorlageId] = useState('')
  const [objektId, setObjektId] = useState(selectedId ?? '')
  const [auswahl, setAuswahl] = useState<EmpfaengerAuswahl>(LEERE_AUSWAHL)
  const [werte, setWerte] = useState<EingabeWerte>({})
  const [unterzeichner, setUnterzeichner] = useState('')
  const [laufId, setLaufId] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)

  const { data: vorlagen, isLoading: vorlagenLaden, error: vorlagenFehler } = useQuery({
    queryKey: ['korrespondenz-vorlagen-aktiv'],
    queryFn: () => vorlagenApi.list({ aktiv: 'true' }),
  })
  const { data: objekte } = useQuery({ queryKey: ['objekte-sidebar'], queryFn: objekteApi.list })
  const { data: mitarbeiter } = useQuery({ queryKey: ['mitarbeiter-liste'], queryFn: () => mitarbeiterApi.list() })

  const moegliche = useMemo(() => serienbriefVorlagen(vorlagen ?? []), [vorlagen])
  const vorlage = moegliche.find(v => v.id === vorlageId) ?? null
  const objektFest = !!vorlage?.objekt

  const { data: versionen } = useQuery({
    queryKey: ['korrespondenz-vorlage-versionen', vorlage?.id],
    queryFn: () => vorlagenApi.versionen(vorlage!.id),
    enabled: !!vorlage,
  })
  const version = versionen?.find(v => v.id === vorlage?.aktive_version) ?? null
  const felder: Eingabefeld[] = version?.eingabefelder ?? []
  const fehlend = fehlendePflichtfelder(felder, werte)

  const { data: lauf } = useQuery({
    queryKey: ['korrespondenz-serienlauf', laufId],
    queryFn: () => serienlaeufeApi.get(laufId!),
    enabled: !!laufId,
    // Nach der Freigabe verarbeitet ein Hintergrund-Task (Mails, Druckstapel).
    refetchInterval: q => (q.state.data?.status === 'freigegeben' ? POLL_MS : false),
  })

  const erzeugen = useMutation({
    mutationFn: () => serienlaeufeApi.erzeugen({
      vorlage_version: vorlage!.aktive_version!,
      objekt: objektId,
      empfaenger_filter: filterAufbauen(auswahl),
      eingabewerte: eingabewerteAufbereiten(felder, werte),
      ...(unterzeichner ? { unterzeichner: Number(unterzeichner) } : {}),
    }),
    onMutate: () => setFehler(null),
    onSuccess: neu => {
      qc.setQueryData(['korrespondenz-serienlauf', neu.id], neu)
      setLaufId(neu.id)
      setSchritt(4)
    },
    onError: async e => setFehler(await korrespondenzFehlerText(e, 'Serienlauf konnte nicht erstellt werden.')),
  })

  const freigeben = useMutation({
    mutationFn: () => serienlaeufeApi.freigeben(laufId!),
    onMutate: () => setFehler(null),
    onSuccess: neu => {
      qc.setQueryData(['korrespondenz-serienlauf', neu.id], neu)
      qc.invalidateQueries({ queryKey: ['korrespondenz-schreiben'] })
    },
    onError: async e => setFehler(await korrespondenzFehlerText(e, 'Freigabe nicht möglich.')),
  })

  function neuBeginnen() {
    setLaufId(null)
    setSchritt(1)
    setFehler(null)
  }

  const gesperrt = !!laufId // Schreiben sind schon erzeugt: Schritte 1–3 lassen sich nicht mehr ändern
  const weiterOk: Record<number, boolean> = {
    1: !!vorlage,
    2: !!objektId,
    3: fehlend.length === 0,
  }

  const stepper: StepperStep[] = SCHRITTE.map((bezeichnung, i) => ({
    nr: i + 1,
    bezeichnung,
    status: i + 1 < schritt ? 'abgeschlossen' : i + 1 === schritt ? 'aktiv' : 'ausstehend',
  }))

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Serienbrief</h1>
        <Link to="/korrespondenz/postausgang" className="ml-auto text-sm text-primary-600 hover:underline">Zum Postausgang</Link>
      </div>

      <Stepper schritte={stepper} />

      <div className="bg-white border border-gray-200 rounded-lg p-5 space-y-4">
        {schritt === 1 && (
          <section aria-label="Vorlage wählen" className="space-y-3">
            <h2 className="font-medium text-gray-800">1. Vorlage wählen</h2>
            {vorlagenLaden && <p className="text-gray-400">Lade Vorlagen…</p>}
            {vorlagenFehler && <p role="alert" className="text-red-600">Vorlagen konnten nicht geladen werden.</p>}
            {vorlagen && moegliche.length === 0 && (
              <p className="text-sm text-amber-700">Keine aktive Vorlage mit freigegebener Version vorhanden.</p>
            )}
            <ul className="space-y-2">
              {moegliche.map(v => (
                <li key={v.id}>
                  <label className={`flex items-start gap-3 border rounded-lg p-3 cursor-pointer ${vorlageId === v.id ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:bg-gray-50'}`}>
                    <input type="radio" name="vorlage" className="mt-1" checked={vorlageId === v.id}
                      disabled={gesperrt}
                      onChange={() => { setVorlageId(v.id); setWerte({}); if (v.objekt) setObjektId(v.objekt) }} />
                    <span className="text-sm">
                      <span className="font-medium">{v.bezeichnung}</span>
                      <span className="block text-gray-500">
                        {ANLASS_LABEL[v.anlass] ?? v.anlass} · {KANAL_LABEL[v.kanal_standard] ?? v.kanal_standard}
                        {' · '}{v.objekt ? (v.objekt_bezeichnung ?? 'Objekt') : 'Global'}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
        )}

        {schritt === 2 && (
          <section aria-label="Empfängerkreis" className="space-y-3">
            <h2 className="font-medium text-gray-800">2. Empfängerkreis</h2>
            <EmpfaengerkreisSchritt objekte={objekte ?? []} objektId={objektId} objektFest={objektFest}
              onObjekt={id => { setObjektId(id); setAuswahl(a => ({ ...a, ausnahmen: {} })) }}
              auswahl={auswahl} onChange={setAuswahl} />
          </section>
        )}

        {schritt === 3 && (
          <section aria-label="Angaben" className="space-y-3">
            <h2 className="font-medium text-gray-800">3. Angaben und Unterzeichner</h2>
            {felder.filter(f => f.name).length === 0 && (
              <p className="text-sm text-gray-500">Diese Vorlage hat keine Eingabefelder.</p>
            )}
            <EingabefelderFormular felder={felder} werte={werte} onChange={setWerte}
              legende="Angaben für alle Schreiben (einmal ausfüllen)" />
            <label className="block text-sm max-w-md">
              <span className="text-gray-700">Unterzeichner</span>
              <select value={unterzeichner} onChange={e => setUnterzeichner(e.target.value)}
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
                <option value="">Ich (angemeldeter Benutzer)</option>
                {(mitarbeiter ?? []).filter(m => m.aktiv).map(m => (
                  <option key={m.id} value={String(m.user_id)}>{m.vollname}</option>
                ))}
              </select>
            </label>
            {fehlend.length > 0 && <p className="text-xs text-gray-500">Pflichtangaben fehlen: {fehlend.join(', ')}</p>}
            <p className="text-xs text-gray-500">
              „Vorschau erzeugen“ legt die Schreiben für den ganzen Empfängerkreis an (noch ohne sie freizugeben oder zu versenden).
            </p>
          </section>
        )}

        {schritt === 4 && lauf && (
          <section aria-label="Vorschau" className="space-y-3">
            <h2 className="font-medium text-gray-800">4. Vorschau</h2>
            <p className="text-sm text-gray-600">{lauf.vorlage.bezeichnung} · {lauf.objekt?.bezeichnung} · {filterBeschreibung(auswahl)}</p>
            <SerienbriefVorschau lauf={lauf} />
          </section>
        )}

        {schritt === 5 && lauf && (
          <FreigabeSchritt lauf={lauf} laeuft={freigeben.isPending} onFreigeben={() => freigeben.mutate()} />
        )}

        {fehler && <p role="alert" className="text-sm text-red-600">{fehler}</p>}

        {/* Navigation */}
        <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-100">
          {/* Nach dem Erzeugen sind Schritt 1–3 gesperrt; nur 5 → 4 (solange noch nicht freigegeben). */}
          {(gesperrt ? schritt === 5 && lauf?.status === 'zur_pruefung' : schritt > 1) && (
            <Button type="button" variant="secondary"
              onClick={() => setSchritt(s => s - 1)}>
              Zurück
            </Button>
          )}
          {schritt < 3 && (
            <Button type="button" disabled={!weiterOk[schritt]} onClick={() => setSchritt(s => s + 1)}>Weiter</Button>
          )}
          {schritt === 3 && (
            <Button type="button" disabled={!weiterOk[3] || !objektId || !vorlage || erzeugen.isPending || gesperrt}
              onClick={() => erzeugen.mutate()}>
              {erzeugen.isPending ? 'Erzeuge Schreiben…' : 'Vorschau erzeugen'}
            </Button>
          )}
          {schritt === 4 && (
            <Button type="button" disabled={!lauf} onClick={() => setSchritt(5)}>Weiter zur Freigabe</Button>
          )}
          {gesperrt && (
            <Button type="button" variant="ghost" className="ml-auto" onClick={neuBeginnen}>Neu beginnen</Button>
          )}
        </div>
        {gesperrt && lauf?.status === 'zur_pruefung' && (
          <p className="text-xs text-gray-500">
            „Neu beginnen“ verwirft die Auswahl. Die bereits angelegten Schreiben dieses Laufs bleiben ungenutzt in der Prüfung und werden nicht versendet.
          </p>
        )}
      </div>
    </div>
  )
}

/** Schritt 5: Zusammenfassung, Freigabe und Ergebnis der Hintergrundverarbeitung. */
function FreigabeSchritt({ lauf, laeuft, onFreigeben }: { lauf: Serienlauf; laeuft: boolean; onFreigeben: () => void }) {
  const inArbeit = lauf.status === 'freigegeben'
  const fertig = lauf.status === 'versendet' || lauf.status === 'teilweise_fehler'
  const je = lauf.zaehler.je_status

  return (
    <section aria-label="Freigabe" className="space-y-3">
      <h2 className="font-medium text-gray-800">5. Freigabe</h2>
      <p className="text-sm text-gray-700">
        {lauf.vorschau.erzeugbar_anzahl} von {lauf.zaehler.gesamt} Schreiben sind erzeugbar
        {lauf.zaehler.nicht_erzeugbar > 0 ? `, ${lauf.zaehler.nicht_erzeugbar} werden übersprungen` : ''}.
        Mit der Freigabe gehen die E-Mails raus und die Briefe landen im Druckstapel.
      </p>

      {lauf.status === 'zur_pruefung' && lauf.blocker.length > 0 && (
        <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <p className="font-medium">Freigabe noch nicht möglich:</p>
          <ul className="list-disc pl-5">{lauf.blocker.map(b => <li key={b}>{b}</li>)}</ul>
        </div>
      )}

      {lauf.status === 'zur_pruefung' && (
        <Button type="button" disabled={!lauf.freigebbar || laeuft} onClick={onFreigeben}>
          {laeuft ? 'Gebe frei…' : `Serienbrief freigeben (${lauf.vorschau.erzeugbar_anzahl})`}
        </Button>
      )}

      {inArbeit && (
        <p role="status" className="rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
          Freigegeben — die Schreiben werden im Hintergrund versendet. Diese Anzeige aktualisiert sich automatisch.
        </p>
      )}

      {fertig && (
        <div role="status" className={`rounded border p-3 text-sm space-y-1 ${lauf.status === 'versendet' ? 'border-green-200 bg-green-50 text-green-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
          <p className="font-medium">
            {lauf.status === 'versendet' ? 'Serienbrief verarbeitet.' : 'Serienbrief verarbeitet — teilweise mit Fehlern.'}
          </p>
          <p>
            {Object.entries(je).map(([status, n]) => `${n} × ${status.replace(/_/g, ' ')}`).join(' · ')}
          </p>
          {lauf.status === 'teilweise_fehler' && (
            <p>
              Offene Fälle stehen im{' '}
              <Link className="underline" to={`/korrespondenz/postausgang?serienlauf=${lauf.id}`}>Postausgang</Link>.
            </p>
          )}
          {lauf.druckstapel_ids.length > 0 && (
            <p>
              Briefe liegen im <Link className="underline" to="/korrespondenz/druckstapel">Druckstapel</Link> zum Druck bereit.
            </p>
          )}
        </div>
      )}

      {fertig && lauf.druck_dokument && (
        <PdfAnzeige titel="Sammel-PDF" dateiname={`Serienbrief-${lauf.id.slice(0, 8)}.pdf`}
          laden={() => druckstapelApi.pdf(lauf.druck_dokument!)} hoehe="h-[60vh]" />
      )}
    </section>
  )
}
