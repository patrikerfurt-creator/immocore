import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { meineEinheiten, PortalEinheit, PortalWegKarte } from '../../api/portal'

/**
 * Einheiten-Ansicht (Spec 1a, Kap. 6.1): WEG-Karten, darin Einheiten-Tabs.
 *
 * Bewusst nur Stammdaten je Einheit — keine Saldo-Karte, kein
 * Buchungsverlauf. Das folgt in Spec 1 (vollständig).
 */
const NUTZUNGSART_LABEL: Record<string, string> = {
  Wohnung: 'Wohnung',
  Gewerbe: 'Gewerbeeinheit',
  Stellplatz: 'Stellplatz',
  Sonstiges: 'Sonstiges',
}

function formatMea(wert: string | null): string {
  if (wert === null) return '—'
  // Der MEA kommt als Dezimalstring mit vier Nachkommastellen; nachlaufende
  // Nullen wegzulassen macht ihn lesbarer, ohne den Wert zu verändern.
  const zahl = Number(wert)
  if (Number.isNaN(zahl)) return wert
  return zahl.toLocaleString('de-DE', { maximumFractionDigits: 4 })
}

function EinheitDetails({ einheit }: { einheit: PortalEinheit }) {
  const zeilen: [string, string][] = [
    ['Einheitsnummer', einheit.einheit_nr],
    ['Lage', einheit.lage || '—'],
    ['Nutzungsart', NUTZUNGSART_LABEL[einheit.nutzungsart] ?? einheit.nutzungsart],
    ['Miteigentumsanteil', formatMea(einheit.miteigentumsanteil)],
    ['Eigentum seit', new Date(einheit.eigentum_seit).toLocaleDateString('de-DE')],
  ]

  return (
    <dl className="divide-y divide-gray-100">
      {zeilen.map(([label, wert]) => (
        <div key={label} className="flex justify-between gap-4 py-2">
          <dt className="text-sm text-gray-500">{label}</dt>
          <dd className="text-sm font-medium text-gray-900 text-right">{wert}</dd>
        </div>
      ))}
    </dl>
  )
}

function WegKarte({ karte }: { karte: PortalWegKarte }) {
  const [aktiv, setAktiv] = useState(0)
  const einheit = karte.einheiten[aktiv] ?? karte.einheiten[0]

  return (
    <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <header className="px-5 py-4 border-b border-gray-100">
        <h2 className="text-base font-semibold text-primary-900">{karte.bezeichnung}</h2>
        <p className="text-sm text-gray-500">
          {karte.strasse}, {karte.plz} {karte.ort}
        </p>
      </header>

      {/* Tabs nur, wenn es in dieser WEG mehrere Einheiten gibt. */}
      {karte.einheiten.length > 1 && (
        <div className="flex flex-wrap gap-1 px-5 pt-3 border-b border-gray-100">
          {karte.einheiten.map((e, i) => (
            <button
              key={e.einheit_id}
              onClick={() => setAktiv(i)}
              className={`px-3 py-1.5 text-sm rounded-t transition-colors ${
                i === aktiv
                  ? 'bg-primary-100 text-primary-900 font-medium'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              Einheit {e.einheit_nr}
            </button>
          ))}
        </div>
      )}

      <div className="px-5 py-3">
        {einheit ? (
          <EinheitDetails einheit={einheit} />
        ) : (
          <p className="text-sm text-gray-500 py-2">Keine Einheiten hinterlegt.</p>
        )}
      </div>
    </section>
  )
}

export function MeineEinheiten() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['portal', 'einheiten'],
    queryFn: meineEinheiten,
  })

  if (isLoading) return <p className="text-sm text-gray-500">Wird geladen…</p>
  if (isError) return <p className="text-sm text-red-600">Die Daten konnten nicht geladen werden.</p>

  if (!data?.length) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <p className="text-sm text-gray-600">
          Zu Ihrem Zugang sind derzeit keine Einheiten hinterlegt. Bitte wenden Sie sich
          an Ihre Hausverwaltung.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {data.map(karte => <WegKarte key={karte.objekt_id} karte={karte} />)}
    </div>
  )
}
