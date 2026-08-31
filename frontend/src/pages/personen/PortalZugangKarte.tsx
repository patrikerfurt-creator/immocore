import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  portalEinladen,
  portalZugaengeLaden,
  portalZugangEntsperren,
  portalZugangSperren,
  PortalZugangVerwaltung,
} from '../../api/portal'
import { Button } from '../../components/ui/Button'

/**
 * Aktion „Portal-Zugang einladen" im internen Bereich (Spec 1a, Kap. 3.1).
 *
 * Der Zugang entsteht ausschließlich hier — eine Selbstregistrierung durch
 * Eigentümer ist bewusst nicht vorgesehen.
 */
const STATUS_LABEL: Record<PortalZugangVerwaltung['status'], string> = {
  eingeladen: 'Eingeladen — noch nicht aktiviert',
  aktiv: 'Aktiv',
  gesperrt: 'Gesperrt',
}

const STATUS_STIL: Record<PortalZugangVerwaltung['status'], string> = {
  eingeladen: 'bg-yellow-100 text-yellow-800',
  aktiv: 'bg-green-100 text-green-800',
  gesperrt: 'bg-red-100 text-red-700',
}

function datum(wert: string | null): string {
  return wert ? new Date(wert).toLocaleString('de-DE') : '–'
}

function fehlertext(fehler: unknown, ersatz: string): string {
  return (fehler as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? ersatz
}

export function PortalZugangKarte({ personId }: { personId: string }) {
  const queryClient = useQueryClient()
  const [meldung, setMeldung] = useState('')
  const [fehler, setFehler] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['portal-zugang', personId],
    queryFn: () => portalZugaengeLaden(personId),
  })
  const zugang = data?.[0]

  function nachAktion(text: string) {
    setMeldung(text)
    setFehler('')
    queryClient.invalidateQueries({ queryKey: ['portal-zugang', personId] })
  }

  const einladen = useMutation({
    mutationFn: () => portalEinladen(personId),
    onSuccess: (neu) => nachAktion(`Einladung an ${neu.email} versendet.`),
    onError: (e) => {
      setFehler(fehlertext(e, 'Die Einladung konnte nicht versendet werden.'))
      setMeldung('')
    },
  })

  const sperren = useMutation({
    mutationFn: () => portalZugangSperren(zugang!.id),
    onSuccess: () => nachAktion('Zugang gesperrt. Laufende Sitzungen wurden beendet.'),
    onError: (e) => setFehler(fehlertext(e, 'Der Zugang konnte nicht gesperrt werden.')),
  })

  const entsperren = useMutation({
    mutationFn: () => portalZugangEntsperren(zugang!.id),
    onSuccess: () => nachAktion('Zugang wieder freigegeben.'),
    onError: (e) => setFehler(fehlertext(e, 'Der Zugang konnte nicht freigegeben werden.')),
  })

  const laeuft = einladen.isPending || sperren.isPending || entsperren.isPending

  return (
    <div className="md:col-span-2 rounded-lg border border-gray-200 p-5 space-y-3">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
        Eigentümer-Portal
      </h2>

      {isLoading ? (
        <p className="text-sm text-gray-400">Laden…</p>
      ) : zugang ? (
        <>
          <div className="flex items-center gap-2">
            <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${STATUS_STIL[zugang.status]}`}>
              {STATUS_LABEL[zugang.status]}
            </span>
            <span className="text-sm text-gray-600">{zugang.email}</span>
          </div>

          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-500">Eingeladen am</dt>
              <dd className="text-gray-800">{datum(zugang.eingeladen_am)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Eingeladen von</dt>
              <dd className="text-gray-800">{zugang.eingeladen_von || '–'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Erstaktivierung</dt>
              <dd className="text-gray-800">{datum(zugang.erstaktivierung_am)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Letzter Login</dt>
              <dd className="text-gray-800">{datum(zugang.letzter_login)}</dd>
            </div>
          </dl>

          {zugang.email_pending && (
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
              E-Mail-Änderung auf <strong>{zugang.email_pending}</strong> ist noch nicht bestätigt.
            </p>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              variant="secondary" size="sm" disabled={laeuft}
              onClick={() => einladen.mutate()}
            >
              Einladung erneut senden
            </Button>
            {zugang.aktiv ? (
              <Button
                variant="danger" size="sm" disabled={laeuft}
                onClick={() => sperren.mutate()}
              >
                Zugang sperren
              </Button>
            ) : (
              <Button
                variant="secondary" size="sm" disabled={laeuft}
                onClick={() => entsperren.mutate()}
              >
                Zugang freigeben
              </Button>
            )}
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-gray-500">
            Für diese Person besteht noch kein Portal-Zugang. Mit der Einladung erhält
            sie einen Aktivierungslink per E-Mail (72 Stunden gültig, einmal verwendbar).
          </p>
          <Button size="sm" disabled={laeuft} onClick={() => einladen.mutate()}>
            {einladen.isPending ? 'Wird versendet…' : 'Portal-Zugang einladen'}
          </Button>
        </>
      )}

      {meldung && <p className="text-sm text-green-700">{meldung}</p>}
      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
    </div>
  )
}
