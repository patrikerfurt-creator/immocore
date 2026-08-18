import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { oeffentlicherAuftragApi } from '../../api/handwerker'
import type { HandwerkerauftragStatus } from '../../types'

const STATUS_LABEL: Record<HandwerkerauftragStatus, string> = {
  entwurf: 'Entwurf', versendet: 'Versendet', angenommen: 'Angenommen',
  abgelehnt: 'Abgelehnt', in_arbeit: 'In Arbeit', abgeschlossen: 'Abgeschlossen',
  storniert: 'Storniert', abgelaufen: 'Abgelaufen',
}

function Karte({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-start sm:items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-6 sm:p-8">
        <div className="mb-5">
          <span className="text-lg font-bold text-primary-900">IMMOCORE</span>
          <p className="text-xs text-gray-400">Demme Immobilien Verwaltung GmbH</p>
        </div>
        {children}
      </div>
    </div>
  )
}

function formatGeld(wert: string | null): string {
  if (wert == null) return '–'
  const n = parseFloat(wert)
  return Number.isNaN(n) ? '–' : `${n.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €`
}

export function AuftragBestaetigung() {
  const { token } = useParams<{ token: string }>()
  const [grund, setGrund] = useState('')
  const [ergebnis, setErgebnis] = useState<{ nummer: string; status: HandwerkerauftragStatus; aktion: 'annehmen' | 'ablehnen' } | null>(null)
  const [konfliktStatus, setKonfliktStatus] = useState<HandwerkerauftragStatus | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['oeffentlich-auftrag', token],
    queryFn: () => oeffentlicherAuftragApi.get(token!),
    enabled: !!token,
    retry: false,
  })

  const bestaetigenMutation = useMutation({
    mutationFn: () => oeffentlicherAuftragApi.bestaetigen(token!, grund || undefined),
    onSuccess: (res) => setErgebnis(res),
    onError: (err) => {
      // @ts-expect-error axios error shape
      const status = err?.response?.status
      // @ts-expect-error axios error shape
      const konflikt = err?.response?.data?.status as HandwerkerauftragStatus | undefined
      if ((status === 409 || status === 410) && konflikt) setKonfliktStatus(konflikt)
    },
  })

  if (isLoading) {
    return <Karte><p className="text-sm text-gray-500">Lade Auftragsdaten…</p></Karte>
  }

  // @ts-expect-error axios error shape
  const httpStatus = error?.response?.status
  if (error && httpStatus === 404) {
    return (
      <Karte>
        <p className="text-sm text-gray-700">
          Dieser Link ist ungültig. Bitte wenden Sie sich an Ihre zuständige Verwaltung.
        </p>
      </Karte>
    )
  }
  if (error) {
    return (
      <Karte>
        <p className="text-sm text-red-600">Die Auftragsdaten konnten nicht geladen werden. Bitte versuchen Sie es später erneut.</p>
      </Karte>
    )
  }
  if (!data) return null

  if (ergebnis) {
    return (
      <Karte>
        <h1 className="text-lg font-semibold text-gray-900 mb-2">
          {ergebnis.aktion === 'annehmen' ? 'Auftrag angenommen' : 'Auftrag abgelehnt'}
        </h1>
        <p className="text-sm text-gray-600 mb-1">
          Vielen Dank für Ihre Rückmeldung zu Auftrag <span className="font-mono">{ergebnis.nummer}</span>.
        </p>
        {ergebnis.aktion === 'annehmen' && (
          <p className="text-sm text-gray-600">
            Bitte geben Sie bei der Rechnungsstellung die Auftragsnummer <span className="font-mono">{ergebnis.nummer}</span> an,
            damit Ihre Rechnung korrekt zugeordnet werden kann.
          </p>
        )}
      </Karte>
    )
  }

  if (konfliktStatus) {
    return (
      <Karte>
        <p className="text-sm text-gray-700">
          Dieser Auftrag hat inzwischen den Status <span className="font-medium">{STATUS_LABEL[konfliktStatus]}</span>.
          Eine erneute Bestätigung über diesen Link ist nicht mehr möglich.
        </p>
      </Karte>
    )
  }

  if (data.bereits_verwendet) {
    return (
      <Karte>
        <p className="text-sm text-gray-700">
          Dieser Bestätigungslink wurde bereits verwendet. Auftrag <span className="font-mono">{data.nummer}</span> hat
          aktuell den Status <span className="font-medium">{STATUS_LABEL[data.status]}</span>.
        </p>
      </Karte>
    )
  }

  if (data.abgelaufen) {
    return (
      <Karte>
        <p className="text-sm text-gray-700">
          Die Frist für diesen Bestätigungslink ist am {new Date(data.gueltig_bis).toLocaleString('de-DE')} abgelaufen.
          Bitte wenden Sie sich an Ihre zuständige Verwaltung, wenn der Auftrag weiterhin aktuell ist.
        </p>
      </Karte>
    )
  }

  return (
    <Karte>
      <h1 className="text-lg font-semibold text-gray-900 mb-1">Auftrag {data.nummer}</h1>
      <p className="text-xs text-gray-400 mb-4">Gültig bis {new Date(data.gueltig_bis).toLocaleString('de-DE')}</p>

      <dl className="text-sm space-y-2 mb-5">
        <div><dt className="text-gray-400">Objekt</dt><dd className="text-gray-800">{data.objekt_bezeichnung}</dd><dd className="text-gray-500 text-xs">{data.objekt_adresse}</dd></div>
        <div><dt className="text-gray-400">Titel</dt><dd className="text-gray-800">{data.titel}</dd></div>
        {data.beschreibung && <div><dt className="text-gray-400">Beschreibung</dt><dd className="text-gray-700 whitespace-pre-wrap">{data.beschreibung}</dd></div>}
        <div><dt className="text-gray-400">Priorität</dt><dd className="text-gray-800 capitalize">{data.prioritaet}</dd></div>
        {data.gewuenscht_ab && <div><dt className="text-gray-400">Wunschtermin</dt><dd className="text-gray-800">{new Date(data.gewuenscht_ab).toLocaleDateString('de-DE')}</dd></div>}
        {data.geschaetzte_kosten && <div><dt className="text-gray-400">Geschätzte Kosten</dt><dd className="text-gray-800">{formatGeld(data.geschaetzte_kosten)}</dd></div>}
      </dl>

      {data.aktion === 'ablehnen' && (
        <div className="mb-4">
          <label className="text-sm font-medium text-gray-700 block mb-1">Grund (optional)</label>
          <textarea
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-20 resize-none"
            value={grund}
            onChange={e => setGrund(e.target.value)}
          />
        </div>
      )}

      <button
        onClick={() => bestaetigenMutation.mutate()}
        disabled={bestaetigenMutation.isPending}
        className={`w-full rounded px-4 py-2.5 text-sm font-medium text-white transition-colors disabled:opacity-50 ${
          data.aktion === 'annehmen' ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'
        }`}
      >
        {bestaetigenMutation.isPending
          ? 'Wird gesendet…'
          : data.aktion === 'annehmen' ? 'Auftrag annehmen' : 'Auftrag ablehnen'}
      </button>

      {bestaetigenMutation.isError && !konfliktStatus && (
        <p className="text-red-600 text-sm mt-3">
          Die Aktion konnte nicht ausgeführt werden. Bitte versuchen Sie es erneut oder wenden Sie sich an Ihre Verwaltung.
        </p>
      )}
    </Karte>
  )
}
