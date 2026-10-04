import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { istAssistentNichtVerfuegbar, vorlagenAssistentApi } from '../../../api/korrespondenz'
import { Button } from '../../../components/ui/Button'
import type { Eingabefeld, VorlagenAnlass, VorlagenAssistentResponse, VorlagenBlock } from '../../../types'
import { ANLASS_OPTIONEN, fehlerMeldung } from '../konstanten'
import { BLOCK_LABEL, blockZusammenfassung, normalisiereBloecke } from './blockModell'

/** Schnellanweisungen für „Mit KI überarbeiten“ (Spec 6). */
export const UEBERARBEITEN_ANWEISUNGEN = ['kürzer', 'förmlicher', 'freundlicher', 'verständlicher']

export type KiDialogModus =
  | { art: 'entwerfen'; bestehendeBloecke: number }
  | { art: 'ueberarbeiten'; block: VorlagenBlock }

export type KiUebernahme =
  | { art: 'anhaengen'; bloecke: VorlagenBlock[]; betreff?: string }
  | { art: 'ersetzen'; bloecke: VorlagenBlock[]; betreff?: string }
  | { art: 'block_ersetzen'; bloecke: VorlagenBlock[] }

interface Props {
  modus: KiDialogModus
  anlass: VorlagenAnlass
  /** Aktuell definierte Eingabefelder — die KI kennt damit `eingabe.*` (ohne Werte). */
  eingabefelder?: Eingabefeld[]
  /** Aktueller Betreff; ein KI-Betreffvorschlag wird nur bei leerem Betreff vorbelegt. */
  aktuellerBetreff?: string
  onUebernehmen: (uebernahme: KiUebernahme) => void
  onSchliessen: () => void
  /** Endpoint meldet „nicht verfügbar“ (kein API-Key) -> Buttons ausblenden. */
  onNichtVerfuegbar: () => void
}

/**
 * KI-Assistent im Vorlagen-Editor. Ergebnis wird erst angezeigt und geprüft
 * (Hinweise des Backends), dann bewusst übernommen — nie automatisch.
 */
export function KiAssistentDialog({
  modus, anlass, eingabefelder, aktuellerBetreff = '', onUebernehmen, onSchliessen, onNichtVerfuegbar,
}: Props) {
  const [gewaehlterAnlass, setGewaehlterAnlass] = useState<VorlagenAnlass>(anlass)
  const [stichworte, setStichworte] = useState('')
  const [ergebnis, setErgebnis] = useState<{ bloecke: VorlagenBlock[]; hinweise: string[]; betreff: string } | null>(null)
  const [betreffUebernehmen, setBetreffUebernehmen] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)

  const anfrage = useMutation({
    mutationFn: () => vorlagenAssistentApi.entwerfen({
      anlass: gewaehlterAnlass,
      stichworte: stichworte.trim(),
      ...(modus.art === 'ueberarbeiten' ? { block: modus.block } : {}),
      ...(eingabefelder && eingabefelder.length > 0 ? { eingabefelder } : {}),
    }),
    onMutate: () => {
      setFehler(null)
      setErgebnis(null)
    },
    onSuccess: (antwort: VorlagenAssistentResponse) => {
      const bloecke = normalisiereBloecke(antwort.bloecke)
      const hinweise = [...(antwort.hinweise ?? [])]
      if (bloecke.length !== (antwort.bloecke ?? []).length) {
        hinweise.push('Einzelne Blöcke der KI-Antwort hatten keine gültige Blockstruktur und wurden verworfen.')
      }
      if (bloecke.length === 0) setFehler('Die KI hat keinen verwertbaren Entwurf geliefert.')
      else {
        const betreff = modus.art === 'entwerfen' ? (antwort.betreff ?? '').trim() : ''
        setErgebnis({ bloecke, hinweise, betreff })
        setBetreffUebernehmen(betreff !== '' && aktuellerBetreff.trim() === '')
      }
    },
    onError: error => {
      if (istAssistentNichtVerfuegbar(error)) {
        onNichtVerfuegbar()
        onSchliessen()
        return
      }
      const timeout = (error as { code?: string })?.code === 'ECONNABORTED'
      setFehler(timeout
        ? 'Zeitüberschreitung: Die KI hat nicht innerhalb von 60 Sekunden geantwortet. Bitte erneut versuchen.'
        : fehlerMeldung(error, 'KI-Aufruf fehlgeschlagen.'))
    },
  })

  const ueberarbeiten = modus.art === 'ueberarbeiten'
  const betreffTeil = ergebnis && betreffUebernehmen && ergebnis.betreff ? { betreff: ergebnis.betreff } : {}
  const kannSenden = stichworte.trim().length > 0 && !anfrage.isPending

  return (
    <div className="fixed inset-0 z-40 bg-black/40 flex items-start justify-center pt-16 px-4" role="dialog"
      aria-modal="true" aria-label={ueberarbeiten ? 'Mit KI überarbeiten' : 'Mit KI entwerfen'}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto p-5 space-y-4">
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-semibold">
            {ueberarbeiten ? 'Block mit KI überarbeiten' : 'Vorlage mit KI entwerfen'}
          </h2>
          <button type="button" onClick={onSchliessen} aria-label="Schließen" className="text-gray-400 hover:text-gray-700">✕</button>
        </div>
        <p className="text-xs text-gray-500">
          Die KI erhält nur Anlass, Ihre Stichworte und die Platzhalterliste (ohne Werte). Der Entwurf
          wird erst nach Ihrer Prüfung übernommen und durchläuft die normale Vorlagenfreigabe.
        </p>

        {ueberarbeiten && (
          <div className="border border-gray-200 rounded p-2 text-sm bg-gray-50">
            <div className="text-xs font-semibold text-gray-500 mb-1">{BLOCK_LABEL[modus.block.typ]}</div>
            <div className="whitespace-pre-wrap">{blockZusammenfassung(modus.block)}</div>
          </div>
        )}

        {!ueberarbeiten && (
          <label className="block text-sm">
            <span className="text-gray-700">Anlass</span>
            <select
              value={gewaehlterAnlass}
              onChange={e => setGewaehlterAnlass(e.target.value as VorlagenAnlass)}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5"
            >
              {ANLASS_OPTIONEN.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        )}

        {ueberarbeiten && (
          <div className="flex flex-wrap gap-1">
            {UEBERARBEITEN_ANWEISUNGEN.map(a => (
              <button key={a} type="button" onClick={() => setStichworte(a)}
                className="text-xs rounded-full border border-gray-300 px-2.5 py-0.5 hover:bg-gray-100">
                {a}
              </button>
            ))}
          </div>
        )}

        <label className="block text-sm">
          <span className="text-gray-700">{ueberarbeiten ? 'Anweisung' : 'Stichworte'}</span>
          <textarea
            value={stichworte}
            onChange={e => setStichworte(e.target.value)}
            rows={3}
            placeholder={ueberarbeiten
              ? 'z. B. kürzer und freundlicher formulieren'
              : 'z. B. freundliche Begrüßung, SEPA-Hinweis, Ansprechpartner nennen'}
            className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5"
          />
        </label>

        <div className="flex items-center gap-2">
          <Button type="button" onClick={() => anfrage.mutate()} disabled={!kannSenden}>
            {anfrage.isPending ? 'KI arbeitet…' : ergebnis ? 'Neu erzeugen' : ueberarbeiten ? 'Überarbeiten' : 'Entwurf erzeugen'}
          </Button>
          {anfrage.isPending && <span className="text-xs text-gray-500">Das kann bis zu 60 Sekunden dauern.</span>}
        </div>

        {fehler && <p role="alert" className="text-sm text-red-600">{fehler}</p>}

        {ergebnis && (
          <div className="space-y-3" aria-label="KI-Ergebnis">
            {ergebnis.hinweise.length > 0 && (
              <div className="border border-amber-300 bg-amber-50 rounded p-3 text-sm" role="status">
                <div className="font-semibold text-amber-900 mb-1">Bitte prüfen</div>
                <ul className="list-disc pl-5 text-amber-900 space-y-0.5">
                  {ergebnis.hinweise.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              </div>
            )}
            {ergebnis.betreff && (
              <label className="flex items-start gap-2 text-sm border border-gray-200 rounded p-2">
                <input type="checkbox" className="mt-1" checked={betreffUebernehmen}
                  onChange={e => setBetreffUebernehmen(e.target.checked)} />
                <span>
                  <span className="text-xs font-semibold text-gray-500 block">Betreff übernehmen</span>
                  {ergebnis.betreff}
                </span>
              </label>
            )}
            <ol className="space-y-2">
              {ergebnis.bloecke.map((b, i) => (
                <li key={i} className="border border-gray-200 rounded p-2 text-sm">
                  <div className="text-xs font-semibold text-gray-500 mb-0.5">{BLOCK_LABEL[b.typ]}</div>
                  <div className="whitespace-pre-wrap">{blockZusammenfassung(b)}</div>
                </li>
              ))}
            </ol>
            <div className="flex flex-wrap gap-2">
              {ueberarbeiten ? (
                <Button type="button" onClick={() => onUebernehmen({ art: 'block_ersetzen', bloecke: ergebnis.bloecke })}>
                  Block ersetzen
                </Button>
              ) : (
                <>
                  <Button type="button" onClick={() => onUebernehmen({ art: 'anhaengen', bloecke: ergebnis.bloecke, ...betreffTeil })}>
                    Blöcke anhängen
                  </Button>
                  {modus.bestehendeBloecke > 0 && (
                    <Button type="button" variant="secondary"
                      onClick={() => {
                        if (window.confirm('Alle bestehenden Blöcke durch den KI-Entwurf ersetzen?')) {
                          onUebernehmen({ art: 'ersetzen', bloecke: ergebnis.bloecke, ...betreffTeil })
                        }
                      }}>
                      Alle Blöcke ersetzen
                    </Button>
                  )}
                </>
              )}
              <Button type="button" variant="ghost" onClick={onSchliessen}>Verwerfen</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
