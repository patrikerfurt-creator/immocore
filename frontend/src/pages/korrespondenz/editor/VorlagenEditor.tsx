import { useMemo, useRef, useState } from 'react'
import type { Editor } from '@tiptap/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  platzhalterApi, textbausteineApi, vorlagenAssistentApi, vorlagenVersionenApi,
} from '../../../api/korrespondenz'
import { Badge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import type {
  Eingabefeld, Vorlage, VorlagenBlock, VorlagenBlockTyp, VorlagenVersion,
} from '../../../types'
import { ANLASS_LABEL, VERSION_STATUS_LABEL, fehlerMeldung } from '../konstanten'
import { BlockRahmen } from './BlockRahmen'
import { platzhalterEinfuegen } from './BlockTextEditor'
import { EingabefeldDesigner } from './EingabefeldDesigner'
import { KiAssistentDialog } from './KiAssistentDialog'
import type { KiDialogModus, KiUebernahme } from './KiAssistentDialog'
import { PdfVorschauPanel } from './PdfVorschauPanel'
import { PlatzhalterSeitenleiste } from './PlatzhalterSeitenleiste'
import {
  BLOCK_LABEL, BLOCK_TYPEN, EINGABEFELD_NAME, eingabefelderAlsPlatzhalter, neuerBlock,
  textQuellen, unbekanntePlatzhalter, zuBloecken, zuEintraegen,
} from './blockModell'
import type { BlockEintrag } from './blockModell'

interface Props {
  vorlage: Vorlage
  version: VorlagenVersion
}

type EinfuegeZiel =
  | { art: 'editor'; editor: Editor }
  | { art: 'betreff' }
  | null

/**
 * Vorlagen-Editor (Spec 8.1): Betreff, Blöcke mit TipTap, Platzhalter-Seitenleiste,
 * Eingabefeld-Designer, KI-Assistent (Abschnitt 6) und PDF-Vorschau.
 * Nur `entwurf`-Versionen sind editierbar; freigegebene werden schreibgeschützt angezeigt.
 */
export function VorlagenEditor({ vorlage, version }: Props) {
  const qc = useQueryClient()
  const readOnly = version.status !== 'entwurf'

  const [betreff, setBetreff] = useState(version.betreff)
  const [eintraege, setEintraege] = useState<BlockEintrag[]>(() => zuEintraegen(version.inhalt))
  const [eingabefelder, setEingabefelder] = useState<Eingabefeld[]>(version.eingabefelder ?? [])
  const [emailText, setEmailText] = useState(version.email_begleittext ?? '')
  const [dirty, setDirty] = useState(false)
  const [meldung, setMeldung] = useState<{ art: 'ok' | 'fehler'; text: string } | null>(null)
  const [ki, setKi] = useState<{ modus: KiDialogModus; blockKey?: string } | null>(null)
  const [kiAus, setKiAus] = useState(false)

  const ziel = useRef<EinfuegeZiel>(null)
  const betreffRef = useRef<HTMLInputElement>(null)

  const { data: registry, isLoading: platzhalterLaedt, error: platzhalterFehler } = useQuery({
    queryKey: ['korrespondenz-platzhalter', vorlage.anlass],
    queryFn: () => platzhalterApi.list(vorlage.anlass),
    staleTime: 5 * 60_000,
  })
  const { data: bausteine } = useQuery({
    queryKey: ['korrespondenz-textbausteine'],
    queryFn: () => textbausteineApi.list(),
    staleTime: 60_000,
  })
  const { data: assistentOk } = useQuery({
    queryKey: ['korrespondenz-assistent-verfuegbar'],
    queryFn: () => vorlagenAssistentApi.verfuegbar(),
    staleTime: Infinity,
    retry: false,
    enabled: !readOnly,
  })
  const kiVerfuegbar = !readOnly && !kiAus && assistentOk !== false

  // Registry-Platzhalter + lokale Eingabefeld-Platzhalter (Gruppe `eingabe`).
  const platzhalter = useMemo(() => {
    const ohneEingabe = (registry ?? []).filter(p => p.gruppe !== 'eingabe')
    return [...ohneEingabe, ...eingabefelderAlsPlatzhalter(eingabefelder)]
  }, [registry, eingabefelder])

  const unbekannt = useMemo(
    () => (registry
      ? unbekanntePlatzhalter(textQuellen(betreff, zuBloecken(eintraege)), platzhalter.map(p => p.name), eingabefelder)
      : []),
    [registry, betreff, eintraege, platzhalter, eingabefelder],
  )

  const feldNamenOk = eingabefelder.every(f => EINGABEFELD_NAME.test(f.name))
    && new Set(eingabefelder.map(f => f.name)).size === eingabefelder.length
  const anlassText = ANLASS_LABEL[vorlage.anlass] ?? vorlage.anlass

  function aendern<T>(setter: (v: T) => void) {
    return (wert: T) => {
      setter(wert)
      setDirty(true)
      setMeldung(null)
    }
  }

  const setzeEintraege = (fn: (alt: BlockEintrag[]) => BlockEintrag[]) => {
    setEintraege(fn)
    setDirty(true)
    setMeldung(null)
  }

  function blockAendern(key: string, block: VorlagenBlock) {
    setzeEintraege(alt => alt.map(e => (e.key === key ? { ...e, block } : e)))
  }
  function blockVerschieben(key: string, richtung: -1 | 1) {
    setzeEintraege(alt => {
      const i = alt.findIndex(e => e.key === key)
      const j = i + richtung
      if (i < 0 || j < 0 || j >= alt.length) return alt
      const neu = [...alt]
      ;[neu[i], neu[j]] = [neu[j], neu[i]]
      return neu
    })
  }
  function blockEntfernen(key: string) {
    setzeEintraege(alt => alt.filter(e => e.key !== key))
  }
  function blockHinzufuegen(typ: VorlagenBlockTyp) {
    setzeEintraege(alt => [...alt, ...zuEintraegen([neuerBlock(typ)])])
  }

  function kiUebernehmen(u: KiUebernahme) {
    const neue = zuEintraegen(u.bloecke)
    if ((u.art === 'anhaengen' || u.art === 'ersetzen') && u.betreff) aendern(setBetreff)(u.betreff)
    if (u.art === 'anhaengen') setzeEintraege(alt => [...alt, ...neue])
    else if (u.art === 'ersetzen') setzeEintraege(() => neue)
    else if (ki?.blockKey) {
      const key = ki.blockKey
      setzeEintraege(alt => alt.flatMap(e => (e.key === key ? neue : [e])))
    }
    setKi(null)
    setMeldung({ art: 'ok', text: 'KI-Entwurf übernommen — bitte prüfen und speichern.' })
  }

  function platzhalterUebernehmen(name: string) {
    const z = ziel.current
    if (z?.art === 'editor') {
      platzhalterEinfuegen(z.editor, name)
    } else if (z?.art === 'betreff' && betreffRef.current) {
      const el = betreffRef.current
      const von = el.selectionStart ?? betreff.length
      const bis = el.selectionEnd ?? von
      const text = `{{ ${name} }}`
      aendern(setBetreff)(betreff.slice(0, von) + text + betreff.slice(bis))
    } else {
      setMeldung({ art: 'fehler', text: 'Bitte zuerst in ein Textfeld oder den Betreff klicken.' })
    }
  }

  const speichern = useMutation({
    mutationFn: () => vorlagenVersionenApi.update(version.id, {
      betreff,
      inhalt: zuBloecken(eintraege),
      eingabefelder,
      email_begleittext: emailText,
    }),
    onSuccess: () => {
      setDirty(false)
      setMeldung({ art: 'ok', text: 'Gespeichert.' })
      qc.invalidateQueries({ queryKey: ['korrespondenz-versionen', vorlage.id] })
    },
    onError: error => setMeldung({ art: 'fehler', text: fehlerMeldung(error, 'Speichern fehlgeschlagen.') }),
  })

  const freigeben = useMutation({
    mutationFn: async () => {
      if (dirty) await speichern.mutateAsync()
      return vorlagenVersionenApi.freigeben(version.id)
    },
    onSuccess: () => {
      setMeldung({ art: 'ok', text: 'Version freigegeben.' })
      qc.invalidateQueries({ queryKey: ['korrespondenz-versionen', vorlage.id] })
      qc.invalidateQueries({ queryKey: ['korrespondenz-vorlage', vorlage.id] })
      qc.invalidateQueries({ queryKey: ['korrespondenz-vorlagen'] })
    },
    onError: error => setMeldung({ art: 'fehler', text: fehlerMeldung(error, 'Freigabe fehlgeschlagen.') }),
  })

  function freigabeBestaetigen() {
    if (!feldNamenOk) {
      setMeldung({ art: 'fehler', text: 'Die Eingabefelder haben ungültige oder doppelte Namen.' })
      return
    }
    if (window.confirm(
      `Version ${version.version} freigeben? Nach der Freigabe ist sie unveränderlich und ersetzt die bisher aktive Version.`,
    )) freigeben.mutate()
  }

  const busy = speichern.isPending || freigeben.isPending

  return (
    <div className="space-y-4">
      {/* Kopfzeile */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            {vorlage.bezeichnung} <span className="text-gray-400 font-normal">— Version {version.version}</span>
          </h2>
          <p className="text-xs text-gray-500">{anlassText} · {vorlage.code}</p>
        </div>
        <Badge value={version.status} label={VERSION_STATUS_LABEL[version.status]} />
        {dirty && <span className="text-xs text-amber-700">Ungespeicherte Änderungen</span>}
        <span className="ml-auto flex gap-2">
          {kiVerfuegbar && (
            <Button type="button" variant="secondary"
              onClick={() => setKi({ modus: { art: 'entwerfen', bestehendeBloecke: eintraege.length } })}>
              ✨ Mit KI entwerfen
            </Button>
          )}
          {!readOnly && (
            <>
              <Button type="button" disabled={!dirty || busy || !feldNamenOk} onClick={() => speichern.mutate()}>
                {speichern.isPending ? 'Speichere…' : 'Speichern'}
              </Button>
              <Button type="button" variant="secondary" disabled={busy} onClick={freigabeBestaetigen}>
                Freigeben
              </Button>
            </>
          )}
        </span>
      </div>

      {readOnly && (
        <p className="text-sm bg-gray-100 border border-gray-200 rounded px-3 py-2">
          Diese Version ist {VERSION_STATUS_LABEL[version.status].toLowerCase()} und nicht mehr änderbar. Für
          Änderungen legen Sie in der Vorlagenverwaltung eine neue Version an. Die PDF-Vorschau steht weiterhin zur Verfügung.
        </p>
      )}
      {meldung && (
        <p role={meldung.art === 'fehler' ? 'alert' : 'status'}
          className={`text-sm ${meldung.art === 'fehler' ? 'text-red-600' : 'text-green-700'}`}>
          {meldung.text}
        </p>
      )}
      {unbekannt.length > 0 && !readOnly && (
        <div role="status" className="text-sm border border-amber-300 bg-amber-50 rounded px-3 py-2 text-amber-900">
          Unbekannte Platzhalter für diesen Anlass: <span className="font-mono">{unbekannt.join(', ')}</span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem] items-start">
        <div className="space-y-4 min-w-0">
          {/* Betreff */}
          <label className="block bg-white border border-gray-200 rounded-lg p-3 text-sm">
            <span className="font-semibold text-gray-800">Betreff</span>
            <input
              ref={betreffRef}
              value={betreff}
              disabled={readOnly}
              onFocus={() => { ziel.current = { art: 'betreff' } }}
              onChange={e => aendern(setBetreff)(e.target.value)}
              placeholder="z. B. Einberufung der Eigentümerversammlung"
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5 disabled:bg-gray-50"
            />
          </label>

          {/* Blöcke */}
          <div className="space-y-3" aria-label="Blöcke">
            {eintraege.length === 0 && (
              <p className="text-sm text-gray-400 bg-white border border-dashed border-gray-300 rounded-lg p-4 text-center">
                Noch keine Blöcke. Fügen Sie unten einen Block hinzu{kiVerfuegbar ? ' oder lassen Sie einen Entwurf von der KI erstellen' : ''}.
              </p>
            )}
            {eintraege.map((e, i) => (
              <BlockRahmen
                key={e.key}
                index={i}
                anzahl={eintraege.length}
                block={e.block}
                readOnly={readOnly}
                bausteine={bausteine ?? []}
                platzhalter={platzhalter}
                kiVerfuegbar={kiVerfuegbar}
                onAendern={b => blockAendern(e.key, b)}
                onVerschieben={r => blockVerschieben(e.key, r)}
                onEntfernen={() => blockEntfernen(e.key)}
                onKiUeberarbeiten={() => setKi({ modus: { art: 'ueberarbeiten', block: e.block }, blockKey: e.key })}
                onFokus={editor => { ziel.current = { art: 'editor', editor } }}
              />
            ))}
          </div>

          {!readOnly && (
            <div className="flex flex-wrap gap-2 items-center" aria-label="Block hinzufügen">
              <span className="text-sm text-gray-600">Block hinzufügen:</span>
              {BLOCK_TYPEN.map(t => (
                <Button key={t} type="button" size="sm" variant="secondary" onClick={() => blockHinzufuegen(t)}>
                  + {BLOCK_LABEL[t]}
                </Button>
              ))}
            </div>
          )}

          <EingabefeldDesigner felder={eingabefelder} onChange={aendern(setEingabefelder)} readOnly={readOnly} />

          <label className="block bg-white border border-gray-200 rounded-lg p-4 text-sm">
            <span className="font-semibold text-gray-800">E-Mail-Begleittext</span>
            <span className="block text-xs text-gray-500">Mailtext, wenn der Brief als PDF-Anhang versendet wird.</span>
            <textarea
              value={emailText}
              disabled={readOnly}
              rows={4}
              onChange={e => aendern(setEmailText)(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5 disabled:bg-gray-50"
            />
          </label>

          <PdfVorschauPanel
            versionId={version.id}
            eingabefelder={eingabefelder}
            vorabSpeichern={async () => {
              if (dirty && !readOnly) await speichern.mutateAsync()
            }}
          />
        </div>

        <div className="lg:sticky lg:top-4">
          <PlatzhalterSeitenleiste
            platzhalter={platzhalter}
            laedt={platzhalterLaedt}
            fehler={platzhalterFehler ? 'Platzhalter konnten nicht geladen werden.' : null}
            readOnly={readOnly}
            onEinfuegen={platzhalterUebernehmen}
          />
        </div>
      </div>

      {ki && (
        <KiAssistentDialog
          modus={ki.modus}
          anlass={vorlage.anlass}
          eingabefelder={eingabefelder}
          aktuellerBetreff={betreff}
          onUebernehmen={kiUebernehmen}
          onSchliessen={() => setKi(null)}
          onNichtVerfuegbar={() => setKiAus(true)}
        />
      )}
    </div>
  )
}
