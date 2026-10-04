import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { korrespondenzFehlerText, platzhalterApi, schreibenApi, vorlagenApi } from '../../../api/korrespondenz'
import { Button } from '../../../components/ui/Button'
import type { SchreibenDetail, VorlagenBlock } from '../../../types'
import { BlockTextEditor } from '../editor/BlockTextEditor'
import { BLOCK_LABEL, blockZusammenfassung, eingabefelderAlsPlatzhalter, hatTextKoerper } from '../editor/blockModell'

interface Props {
  schreiben: SchreibenDetail
  /** Nach erfolgreichem Speichern (Backend hat neu gerendert) — z. B. PDF-Vorschau neu laden. */
  onGespeichert: (schreiben: SchreibenDetail) => void
}

/**
 * Textanpassung eines Einzelschreibens (Spec 7.2) — nur bei `einzeln_bearbeitbar` und Status
 * `zur_pruefung`. Bearbeitbar sind die Textkörper; die übrigen Blöcke (Baustein, Tabelle, Liste,
 * Seitenumbruch) bleiben unverändert und werden nur angezeigt. Ausgangspunkt ist der bisher
 * angepasste Inhalt, sonst der Inhalt der freigegebenen Vorlagenversion.
 */
export function SchreibenTextAnpassung({ schreiben, onGespeichert }: Props) {
  const [bloecke, setBloecke] = useState<VorlagenBlock[] | null>(schreiben.inhalt_angepasst)
  const [geaendert, setGeaendert] = useState(false)
  const [neuVersion, setNeuVersion] = useState(0)
  const [fehler, setFehler] = useState<string | null>(null)

  const { data: versionen, isLoading, error } = useQuery({
    queryKey: ['korrespondenz-vorlage-versionen', schreiben.vorlage.id],
    queryFn: () => vorlagenApi.versionen(schreiben.vorlage.id),
  })
  const { data: registry } = useQuery({
    queryKey: ['korrespondenz-platzhalter', schreiben.vorlage.anlass],
    queryFn: () => platzhalterApi.list(schreiben.vorlage.anlass),
  })

  const version = versionen?.find(v => v.status === 'freigegeben') ?? null
  const basis: VorlagenBlock[] | null = bloecke ?? version?.inhalt ?? null

  const platzhalter = useMemo(
    () => [...(registry ?? []).filter(p => p.gruppe !== 'eingabe'), ...eingabefelderAlsPlatzhalter(version?.eingabefelder ?? [])],
    [registry, version],
  )

  const speichern = useMutation({
    mutationFn: () => schreibenApi.anpassen(schreiben.id, basis!),
    onMutate: () => setFehler(null),
    onSuccess: neu => {
      setGeaendert(false)
      onGespeichert(neu)
    },
    onError: async e => setFehler(await korrespondenzFehlerText(e, 'Text konnte nicht gespeichert werden.')),
  })

  function aendere(index: number, block: VorlagenBlock) {
    setBloecke((basis ?? []).map((b, i) => (i === index ? block : b)))
    setGeaendert(true)
  }

  function zuruecksetzen() {
    setBloecke(schreiben.inhalt_angepasst)
    setGeaendert(false)
    setFehler(null)
    setNeuVersion(n => n + 1) // Editoren laden ihren Inhalt nur beim Mounten
  }

  if (isLoading) return <p className="text-sm text-gray-400">Lade Vorlagentext…</p>
  if (error) return <p role="alert" className="text-sm text-red-600">Der Vorlagentext konnte nicht geladen werden.</p>
  if (!basis) {
    return <p className="text-sm text-amber-700">Die Vorlage hat keine freigegebene Version — der Text kann nicht angepasst werden.</p>
  }

  return (
    <section className="space-y-3" aria-label="Text anpassen">
      <p className="text-xs text-gray-500">
        Die Anpassung gilt nur für dieses Schreiben, die Vorlage bleibt unverändert.
      </p>
      {basis.map((block, i) => (
        <div key={`${neuVersion}-${i}`} className="border border-gray-200 rounded p-2 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            {i + 1}. {BLOCK_LABEL[block.typ]}
          </p>
          {hatTextKoerper(block) ? (
            <>
              {block.typ === 'anlage_seite' && <p className="text-xs text-gray-500">Anlage: {block.titel}</p>}
              {block.typ === 'bedingt' && (
                <p className="text-xs text-gray-500">Erscheint nur, wenn <span className="font-mono">{block.bedingung}</span> gilt.</p>
              )}
              <BlockTextEditor label={`Text Block ${i + 1}`} inhalt={block.inhalt} platzhalter={platzhalter}
                onChange={inhalt => aendere(i, { ...block, inhalt })} />
            </>
          ) : (
            <p className="text-sm text-gray-600 whitespace-pre-wrap">{blockZusammenfassung(block)}</p>
          )}
        </div>
      ))}
      {fehler && <p role="alert" className="text-sm text-red-600">{fehler}</p>}
      <div className="flex gap-2">
        <Button type="button" disabled={!geaendert || speichern.isPending} onClick={() => speichern.mutate()}>
          {speichern.isPending ? 'Speichere…' : 'Text speichern'}
        </Button>
        <Button type="button" variant="secondary" disabled={!geaendert || speichern.isPending} onClick={zuruecksetzen}>
          Änderungen verwerfen
        </Button>
      </div>
    </section>
  )
}
