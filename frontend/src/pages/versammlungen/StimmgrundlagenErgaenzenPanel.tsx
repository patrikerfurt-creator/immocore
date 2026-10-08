import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import { versammlungApi } from '../../api/versammlung'
import { Button } from '../../components/ui/Button'
import type { EVDetail } from '../../types'

function fehlertext(error: any, fallback: string) {
  return error?.response?.data?.detail
    ?? (typeof error?.response?.data === 'object'
      ? JSON.stringify(error.response.data)
      : fallback)
}

// Ergänzt einer EV weitere Stimmgrundlagen über den
// stimmgrundlage-hinzufuegen-Endpunkt. Wird sowohl direkt nach der EV-Anlage
// (variant='anlage') als auch nachträglich in der Detailansicht
// (variant='nachtrag') genutzt. Serverseitig nur solange die Einladung nicht
// versendet ist (Status vor Versand) — die Detailansicht blendet das Panel
// außerhalb dieses Zustands aus.
export function StimmgrundlagenErgaenzenPanel({
  ev,
  onFertig,
  variant = 'nachtrag',
}: {
  ev: EVDetail
  onFertig: () => void
  variant?: 'anlage' | 'nachtrag'
}) {
  const [ausgewaehlt, setAusgewaehlt] = useState<string[]>([])
  const [standard, setStandard] = useState('')
  const [fehler, setFehler] = useState('')

  const { data: verteilerschluessel } = useQuery({
    queryKey: ['verteilerschluessel', ev.objekt],
    queryFn: () => objekteApi.verteilerschluessel({ objekt: ev.objekt }),
    staleTime: 60_000,
  })

  // Verbrauchsschlüssel sind keine zulässige Stimmgrundlage (Spec v1.1 Kap. 2)
  // und bereits vergebene Grundlagen (Kopfprinzip bzw. derselbe
  // Verteilerschlüssel) dürfen wegen der Unique-Constraints je EV nicht
  // doppelt angeboten werden.
  const vorhandeneVsIds = new Set(
    ev.stimmgrundlagen.filter(g => g.verteilerschluessel).map(g => g.verteilerschluessel as string),
  )
  const hatKopfprinzip = ev.stimmgrundlagen.some(g => g.ist_kopfprinzip)

  const optionen: { id: string; label: string }[] = [
    ...(hatKopfprinzip ? [] : [{ id: 'kopf', label: 'Kopfprinzip — eine Stimme je Eigentümer' }]),
    ...(verteilerschluessel ?? [])
      .filter(vs => vs.aktiv && vs.vs_typ !== 'verbrauch' && !vorhandeneVsIds.has(vs.id))
      .map(vs => ({ id: vs.id, label: `${vs.schluessel} ${vs.bezeichnung}` })),
  ]

  const toggle = (id: string) => {
    setAusgewaehlt(alt => (alt.includes(id) ? alt.filter(x => x !== id) : [...alt, id]))
    if (standard === id) setStandard('')
  }

  const speichern = useMutation({
    mutationFn: async () => {
      for (const id of ausgewaehlt) {
        // eslint-disable-next-line no-await-in-loop -- bewusst sequenziell:
        // ist_standard darf serverseitig nur je Aufruf einmal umgesetzt werden.
        await versammlungApi.stimmgrundlageHinzufuegen(ev.id, id === 'kopf'
          ? { ist_kopfprinzip: true, ist_standard: standard === id }
          : { verteilerschluessel: id, ist_standard: standard === id })
      }
    },
    onSuccess: () => {
      setFehler('')
      onFertig()
    },
    onError: (e: any) => setFehler(fehlertext(e, 'Stimmgrundlagen konnten nicht ergänzt werden.')),
  })

  const standardGrundlage = ev.stimmgrundlagen.find(g => g.ist_standard)?.bezeichnung_anzeige

  return (
    <div className="space-y-3 rounded border border-gray-200 bg-gray-50 p-4">
      {variant === 'anlage' ? (
        <p className="text-sm text-gray-700">
          „{ev.arbeitsname || ev.art_display}" wurde angelegt — Standard-Stimmgrundlage
          ist „{standardGrundlage}". Weicht die Teilungserklärung für einzelne
          Tagesordnungspunkte davon ab, können hier weitere Stimmgrundlagen ergänzt
          werden — optional, das lässt sich auch später an der Versammlung selbst
          nachholen.
        </p>
      ) : (
        <p className="text-sm text-gray-700">
          Weitere Stimmgrundlage für diese Versammlung ergänzen — z. B. ein
          Verteilerschlüssel, der laut Teilungserklärung für einzelne
          Tagesordnungspunkte gilt. Danach ist sie je TOP im Dropdown auswählbar.
        </p>
      )}
      {optionen.length === 0 && (
        <p className="text-sm text-gray-500">Keine weiteren Stimmgrundlagen verfügbar.</p>
      )}
      <div className="space-y-1">
        {optionen.map(o => (
          <div key={o.id} className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={ausgewaehlt.includes(o.id)}
                onChange={() => toggle(o.id)}
              />
              {o.label}
            </label>
            {ausgewaehlt.includes(o.id) && (
              <label className="flex items-center gap-1 text-xs text-gray-600">
                <input
                  type="radio"
                  name="standard-stimmgrundlage-ergaenzen"
                  checked={standard === o.id}
                  onChange={() => setStandard(o.id)}
                />
                als neue Standard-Stimmgrundlage für den ersten TOP
              </label>
            )}
          </div>
        ))}
      </div>
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
      <div className="flex gap-2">
        <Button
          onClick={() => speichern.mutate()}
          disabled={ausgewaehlt.length === 0 || speichern.isPending}
        >
          {speichern.isPending ? 'Speichert…' : 'Stimmgrundlagen ergänzen'}
        </Button>
        <Button variant="secondary" onClick={onFertig}>
          {ausgewaehlt.length === 0 ? 'Fertig' : 'Ohne weitere Stimmgrundlagen fortfahren'}
        </Button>
      </div>
    </div>
  )
}
