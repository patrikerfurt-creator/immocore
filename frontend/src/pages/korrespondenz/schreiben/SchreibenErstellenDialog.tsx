import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { korrespondenzFehlerText, schreibenApi, vorlagenApi } from '../../../api/korrespondenz'
import { personenApi } from '../../../api/personen'
import { Button } from '../../../components/ui/Button'
import type {
  Eingabefeld, PersonList, SchreibenCreatePayload, SchreibenDetail, SchreibenKanal, Vorlage, VorlagenAnlass,
} from '../../../types'
import { eingabewerteAufbereiten } from '../editor/PdfVorschauPanel'
import { ANLASS_LABEL } from '../konstanten'
import { EingabefelderFormular } from './EingabefelderFormular'
import {
  KANAL_WAHL, fehlendePflichtfelder, istMahnAnlass, type EingabeWerte,
} from './schreibenKonstanten'

export interface SchreibenKontext {
  /** Empfänger, wenn schon bekannt (Person-/Einheit-/Vorgangsansicht); sonst Personensuche im Dialog. */
  person?: { id: string; name: string } | null
  einheitId?: string | null
  objektId?: string | null
  eigentumsverhaeltnisId?: string | null
  vorgangId?: string | null
  /** Fester Anlass (z. B. `vorgang_antwort`); ohne Angabe wählt der Nutzer den Anlass. */
  anlass?: VorlagenAnlass | null
}

interface Props extends SchreibenKontext {
  onClose: () => void
  /** Nach erfolgreichem Anlegen (auch bei „nicht erzeugbar“), z. B. zum Neuladen der Vorgangsansicht. */
  onErstellt?: (schreiben: SchreibenDetail) => void
}

/** Vorlagen, die im Dialog wählbar sind: aktiv, mit freigegebener Version, passend zu Objekt und Anlass. */
export function waehlbareVorlagen(
  vorlagen: Vorlage[], objektId: string | null | undefined, anlass: VorlagenAnlass | null | undefined,
): Vorlage[] {
  const passend = vorlagen.filter(v => {
    if (!v.aktiv || !v.aktive_version) return false
    if (objektId && v.objekt && v.objekt !== objektId) return false
    if (anlass) return v.anlass === anlass
    // Mahnungen kommen aus dem Mahnwesen, Vorgangsantworten nur aus dem Vorgang.
    return !istMahnAnlass(v.anlass) && v.anlass !== 'vorgang_antwort'
  })
  // Gleicher Code global und objektbezogen: das Backend löst zur objektbezogenen Vorlage auf.
  const je: Map<string, Vorlage> = new Map()
  for (const v of passend) {
    const vorhanden = je.get(v.code)
    if (!vorhanden || (objektId && v.objekt === objektId && vorhanden.objekt !== objektId)) je.set(v.code, v)
  }
  return [...je.values()]
}

/** Dialog „Schreiben erstellen“ (Spec 7.1, 8.1): Vorlage nach Anlass, Eingabefelder, Kanal. */
export function SchreibenErstellenDialog({
  person: personVorgabe = null, einheitId = null, objektId = null, eigentumsverhaeltnisId = null,
  vorgangId = null, anlass = null, onClose, onErstellt,
}: Props) {
  const [person, setPerson] = useState<{ id: string; name: string } | null>(personVorgabe)
  const [suche, setSuche] = useState('')
  const [evId, setEvId] = useState(eigentumsverhaeltnisId ?? '')
  const [gewaehlterAnlass, setGewaehlterAnlass] = useState<string>(anlass ?? '')
  const [vorlageId, setVorlageId] = useState('')
  const [werte, setWerte] = useState<EingabeWerte>({})
  const [kanal, setKanal] = useState<'' | SchreibenKanal>('')
  const [fehler, setFehler] = useState<string | null>(null)
  const [erstellt, setErstellt] = useState<SchreibenDetail | null>(null)

  const { data: treffer } = useQuery({
    queryKey: ['korrespondenz-schreiben-personen', suche],
    queryFn: () => personenApi.list({ search: suche }),
    enabled: !person && suche.trim().length >= 2,
    staleTime: 10_000,
  })

  // Einheit-Auswahl nur, wenn der Kontext keine Einheit vorgibt.
  const { data: eigentumsverhaeltnisse } = useQuery({
    queryKey: ['korrespondenz-schreiben-ev', person?.id],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ person: person!.id }),
    enabled: !!person && !einheitId && !vorgangId,
  })
  const gewaehltesEv = (eigentumsverhaeltnisse ?? []).find(ev => ev.id === evId)

  const { data: vorlagen, isLoading: vorlagenLaden, error: vorlagenFehler } = useQuery({
    queryKey: ['korrespondenz-vorlagen-aktiv'],
    queryFn: () => vorlagenApi.list({ aktiv: 'true' }),
  })

  const moegliche = useMemo(
    () => waehlbareVorlagen(vorlagen ?? [], objektId, anlass),
    [vorlagen, objektId, anlass],
  )
  const anlaesse = useMemo(() => [...new Set(moegliche.map(v => v.anlass))], [moegliche])
  const zurAuswahl = moegliche.filter(v => !gewaehlterAnlass || v.anlass === gewaehlterAnlass)
  const vorlage = moegliche.find(v => v.id === vorlageId) ?? null

  const { data: versionen } = useQuery({
    queryKey: ['korrespondenz-vorlage-versionen', vorlage?.id],
    queryFn: () => vorlagenApi.versionen(vorlage!.id),
    enabled: !!vorlage,
  })
  const felder: Eingabefeld[] = useMemo(
    () => versionen?.find(v => v.id === vorlage?.aktive_version)?.eingabefelder ?? [],
    [versionen, vorlage],
  )
  const fehlend = fehlendePflichtfelder(felder, werte)

  const erstellen = useMutation({
    mutationFn: () => {
      const einheit = einheitId ?? gewaehltesEv?.einheit ?? null
      const payload: SchreibenCreatePayload = {
        vorlage_code: vorlage!.code,
        empfaenger: person!.id,
        ...(objektId ? { objekt: objektId } : {}),
        ...(einheit ? { einheit } : {}),
        ...((eigentumsverhaeltnisId || gewaehltesEv?.id)
          ? { eigentumsverhaeltnis: eigentumsverhaeltnisId ?? gewaehltesEv!.id } : {}),
        ...(vorgangId ? { vorgang: vorgangId } : {}),
        eingabewerte: eingabewerteAufbereiten(felder, werte),
        ...(kanal ? { kanal } : {}),
      }
      return schreibenApi.create(payload)
    },
    onMutate: () => setFehler(null),
    onSuccess: schreiben => {
      setErstellt(schreiben)
      onErstellt?.(schreiben)
    },
    onError: async error => setFehler(await korrespondenzFehlerText(error, 'Schreiben konnte nicht erstellt werden.')),
  })

  const bereit = !!person && !!vorlage && fehlend.length === 0 && !erstellen.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto">
      <div role="dialog" aria-modal="true" aria-label="Schreiben erstellen"
        className="mt-12 w-full max-w-xl rounded-lg bg-white shadow-xl">
        <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4">
          <h2 className="text-base font-semibold text-gray-900">Schreiben erstellen</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600" aria-label="Schließen">✕</button>
        </div>

        {erstellt ? (
          <div className="px-5 py-4 space-y-3">
            {erstellt.nicht_erzeugbar || (erstellt.status === 'entwurf' && erstellt.fehler) ? (
              <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 space-y-1">
                <p className="font-medium">Das Schreiben {erstellt.nummer} ist nicht erzeugbar.</p>
                <p>{erstellt.fehler}</p>
                <p className="text-xs text-red-600">Es steht im Postausgang unter „Nicht erzeugbar“.</p>
              </div>
            ) : (
              <div role="status" className="rounded border border-green-200 bg-green-50 p-3 text-sm text-green-800">
                Das Schreiben {erstellt.nummer} liegt zur Prüfung im Postausgang.
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={onClose}>Schließen</Button>
              <Link to={`/korrespondenz/postausgang/${erstellt.id}`}
                className="inline-flex items-center rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700">
                Im Postausgang öffnen
              </Link>
            </div>
          </div>
        ) : (
          <form className="px-5 py-4 space-y-4" onSubmit={e => { e.preventDefault(); if (bereit) erstellen.mutate() }}>
            {/* Empfänger */}
            {person ? (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-gray-500">Empfänger:</span>
                <span className="font-medium">{person.name}</span>
                {!personVorgabe && (
                  <button type="button" className="text-primary-600 hover:underline text-xs"
                    onClick={() => { setPerson(null); setSuche(''); setEvId('') }}>ändern</button>
                )}
              </div>
            ) : (
              <div>
                <input type="search" value={suche} onChange={e => setSuche(e.target.value)}
                  placeholder="Empfänger suchen (Name, Nummer)…" aria-label="Empfänger suchen"
                  className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" />
                {treffer && treffer.length > 0 && (
                  <ul className="border border-gray-200 rounded mt-1 max-h-40 overflow-auto text-sm" aria-label="Personen-Treffer">
                    {(treffer as PersonList[]).slice(0, 20).map(p => (
                      <li key={p.id}>
                        <button type="button" className="w-full text-left px-2 py-1 hover:bg-gray-50"
                          onClick={() => setPerson({ id: p.id, name: p.name })}>
                          {p.name} <span className="text-gray-400">({p.personennummer})</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {person && !einheitId && !vorgangId && (eigentumsverhaeltnisse?.length ?? 0) > 0 && (
              <label className="block text-sm">
                <span className="text-gray-700">Einheit (optional)</span>
                <select value={evId} onChange={e => setEvId(e.target.value)}
                  className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
                  <option value="">— keine —</option>
                  {eigentumsverhaeltnisse!.map(ev => (
                    <option key={ev.id} value={ev.id}>Einheit {ev.einheit_nr}{ev.ende ? ' (beendet)' : ''}</option>
                  ))}
                </select>
              </label>
            )}

            {/* Anlass + Vorlage */}
            {vorlagenLaden && <p className="text-sm text-gray-400">Lade Vorlagen…</p>}
            {vorlagenFehler && <p role="alert" className="text-sm text-red-600">Vorlagen konnten nicht geladen werden.</p>}
            {!anlass && anlaesse.length > 1 && (
              <label className="block text-sm">
                <span className="text-gray-700">Anlass</span>
                <select value={gewaehlterAnlass}
                  onChange={e => { setGewaehlterAnlass(e.target.value); setVorlageId(''); setWerte({}) }}
                  className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
                  <option value="">— alle —</option>
                  {anlaesse.map(a => <option key={a} value={a}>{ANLASS_LABEL[a] ?? a}</option>)}
                </select>
              </label>
            )}
            {anlass && (
              <p className="text-sm text-gray-600">Anlass: <span className="font-medium">{ANLASS_LABEL[anlass] ?? anlass}</span></p>
            )}
            <label className="block text-sm">
              <span className="text-gray-700">Vorlage</span>
              <select value={vorlageId} onChange={e => { setVorlageId(e.target.value); setWerte({}) }}
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
                <option value="">— wählen —</option>
                {zurAuswahl.map(v => (
                  <option key={v.id} value={v.id}>
                    {v.bezeichnung}{v.objekt ? ` (${v.objekt_bezeichnung ?? 'Objekt'})` : ''}
                  </option>
                ))}
              </select>
            </label>
            {vorlagen && zurAuswahl.length === 0 && (
              <p className="text-sm text-amber-700">Keine aktive Vorlage mit freigegebener Version für diesen Anlass.</p>
            )}
            {vorlage?.einzeln_bearbeitbar && (
              <p className="text-xs text-gray-500">Der Text kann vor der Freigabe im Postausgang angepasst werden.</p>
            )}

            <EingabefelderFormular felder={felder} werte={werte} onChange={setWerte} />

            <label className="block text-sm">
              <span className="text-gray-700">Kanal</span>
              <select value={kanal} onChange={e => setKanal(e.target.value as '' | SchreibenKanal)}
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5">
                {KANAL_WAHL.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
            </label>
            <p className="text-xs text-gray-500">E-Mail nur mit Zustimmung und E-Mail-Adresse des Empfängers, sonst Brief.</p>

            {fehler && <p role="alert" className="text-sm text-red-600">{fehler}</p>}
            {fehlend.length > 0 && vorlage && (
              <p className="text-xs text-gray-500">Pflichtangaben fehlen: {fehlend.join(', ')}</p>
            )}

            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={onClose}>Abbrechen</Button>
              <Button type="submit" disabled={!bereit}>
                {erstellen.isPending ? 'Erstelle…' : 'Schreiben erstellen'}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

interface ButtonProps extends SchreibenKontext {
  onErstellt?: (schreiben: SchreibenDetail) => void
  variant?: 'primary' | 'secondary'
  label?: string
}

/** Button „Schreiben erstellen“ für Person-, Einheit- und Vorgangsansicht (öffnet den Dialog). */
export function SchreibenErstellenButton({ variant = 'secondary', label = 'Schreiben erstellen', onErstellt, ...kontext }: ButtonProps) {
  const [offen, setOffen] = useState(false)
  return (
    <>
      <Button type="button" variant={variant} onClick={() => setOffen(true)}>{label}</Button>
      {offen && <SchreibenErstellenDialog {...kontext} onErstellt={onErstellt} onClose={() => setOffen(false)} />}
    </>
  )
}
