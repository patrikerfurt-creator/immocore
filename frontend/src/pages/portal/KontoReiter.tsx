import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { meinSaldo, meineFaelligkeiten, PortalFaelligkeit, PortalSaldo } from '../../api/portal'

/**
 * Konto-Reiter im Eigentümer-Portal (Spec 1, Kap. 8.1).
 *
 * Personenkonto-Saldo und offene Fälligkeiten kommen unpaginiert für die
 * gesamte Person; gefiltert wird hier ausschließlich clientseitig auf die
 * gerade gewählte Einheit — `MeineEinheiten` fragt dieselben Endpunkte für
 * die Kennzahl-Karten ab (react-query dedupliziert über den gemeinsamen
 * queryKey, es gibt also keinen doppelten Request).
 */

/** Geldbetrag (String mit 2 Nachkommastellen) deutsch formatiert. Auch von
 * `MeineEinheiten` für die Kennzahl-Karten genutzt. */
export function formatGeld(betrag: string): string {
  const zahl = Number(betrag)
  if (Number.isNaN(zahl)) return betrag
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(zahl)
}

/** Auch von `MeineEinheiten` für die Kennzahl-Karte "Nächste Fälligkeit" genutzt. */
export function formatDatum(iso: string): string {
  const datum = new Date(iso)
  if (Number.isNaN(datum.getTime())) return iso
  return datum.toLocaleDateString('de-DE')
}

/** Die Periode ist serverseitig ein DateField und kommt deshalb als
 *  "YYYY-MM-DD" (der Monatserste) — angezeigt wird nur Monat und Jahr, der
 *  Tag trägt keine Information. Unerwartete Formate bleiben unverändert. */
function formatPeriode(periode: string): string {
  const treffer = periode.match(/^(\d{4})-(\d{2})/)
  if (!treffer) return periode
  const datum = new Date(Number(treffer[1]), Number(treffer[2]) - 1, 1)
  return datum.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' })
}

function SaldoKarte({ saldo }: { saldo: PortalSaldo }) {
  const [aufschluesselungOffen, setAufschluesselungOffen] = useState(false)
  const istGuthaben = Number(saldo.gesamtsaldo) >= 0

  return (
    <div className="bg-white border border-portal-line rounded-[10px] px-5 py-4">
      <div className="text-xs text-portal-soft mb-1">Personenkonto {saldo.kontonummer}</div>
      <div className={`text-2xl font-semibold ${istGuthaben ? 'text-portal-credit' : 'text-portal-debit'}`}>
        {formatGeld(saldo.gesamtsaldo)}
      </div>
      <p className="text-[13.5px] text-portal-soft mt-1">
        {istGuthaben
          ? 'Guthaben — Sie haben derzeit mehr eingezahlt, als benötigt wird.'
          : 'Rückstand — es sind derzeit noch Zahlungen offen.'}
      </p>
      <p className="text-[11.5px] text-portal-soft mt-1">Stand: {formatDatum(saldo.stand_am)}</p>

      {saldo.aufschluesselung.length > 0 && (
        <>
          <button
            onClick={() => setAufschluesselungOffen(v => !v)}
            className="mt-3 text-[13px] font-medium text-portal-brand hover:underline"
          >
            {aufschluesselungOffen ? 'Aufschlüsselung ausblenden' : 'Aufschlüsselung anzeigen'}
          </button>
          {aufschluesselungOffen && (
            <dl className="mt-2 border-t border-portal-line pt-2">
              {saldo.aufschluesselung.map((zeile, i) => (
                <div key={i} className="flex justify-between gap-4 py-1.5 text-[13px]">
                  <dt className="text-portal-soft">{zeile.bezeichnung}</dt>
                  <dd className="font-medium text-portal-ink">{formatGeld(zeile.betrag)}</dd>
                </div>
              ))}
            </dl>
          )}
        </>
      )}
    </div>
  )
}

function FaelligkeitenListe({ faelligkeiten }: { faelligkeiten: PortalFaelligkeit[] }) {
  if (!faelligkeiten.length) {
    return (
      <p className="mt-3 px-4 py-3 text-[13.5px] text-portal-soft bg-white border border-dashed border-portal-line rounded-[10px]">
        Für diese Einheit sind derzeit keine Fälligkeiten offen.
      </p>
    )
  }

  const sortiert = [...faelligkeiten].sort((a, b) => a.faellig_am.localeCompare(b.faellig_am))

  return (
    <div className="mt-3 bg-white border border-portal-line rounded-[10px] divide-y divide-portal-line">
      {sortiert.map((f, i) => (
        <div key={i} className="flex justify-between gap-4 px-4 py-2.5">
          <div>
            <div className="text-[13.5px] font-medium text-portal-ink">{f.bezeichnung}</div>
            <div className="text-[11.5px] text-portal-soft">
              {formatPeriode(f.periode)} · fällig am {formatDatum(f.faellig_am)}
              {f.ueberfaellig && <span className="ml-1.5 text-portal-debit">· überfällig</span>}
            </div>
          </div>
          <div className={`text-[13.5px] font-semibold shrink-0 ${f.ueberfaellig ? 'text-portal-debit' : 'text-portal-ink'}`}>
            {formatGeld(f.offener_betrag)}
          </div>
        </div>
      ))}
    </div>
  )
}

export function KontoReiter({ einheitId }: { einheitId: string }) {
  const saldoQuery = useQuery({ queryKey: ['portal', 'saldo'], queryFn: meinSaldo })
  const faelligkeitenQuery = useQuery({ queryKey: ['portal', 'faelligkeiten'], queryFn: meineFaelligkeiten })

  if (saldoQuery.isLoading || faelligkeitenQuery.isLoading) {
    return <p className="mt-4 text-sm text-portal-soft">Wird geladen…</p>
  }
  if (saldoQuery.isError || faelligkeitenQuery.isError) {
    return <p className="mt-4 text-sm text-portal-debit">Die Kontodaten konnten nicht geladen werden.</p>
  }

  const saldo = saldoQuery.data?.find(s => s.einheit_id === einheitId)
  const faelligkeiten = (faelligkeitenQuery.data ?? []).filter(f => f.einheit_id === einheitId)

  return (
    <div className="mt-4">
      {saldo ? (
        <SaldoKarte saldo={saldo} />
      ) : (
        <p className="px-5 py-4 text-[13.5px] text-portal-soft bg-white border border-dashed border-portal-line rounded-[10px]">
          Für diese Einheit ist noch kein Personenkonto hinterlegt.
        </p>
      )}

      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-portal-soft mt-6 mb-2">
        Nächste Fälligkeiten
      </p>
      <FaelligkeitenListe faelligkeiten={faelligkeiten} />
    </div>
  )
}

/** Für die Kennzahl-Karte "Aktueller Saldo" in `MeineEinheiten`. */
export function findSaldoFuerEinheit(saldi: PortalSaldo[] | undefined, einheitId: string): PortalSaldo | undefined {
  return saldi?.find(s => s.einheit_id === einheitId)
}

/** Für die Kennzahl-Karte "Nächste Fälligkeit" in `MeineEinheiten`. */
export function findNaechsteFaelligkeit(
  faelligkeiten: PortalFaelligkeit[] | undefined, einheitId: string,
): PortalFaelligkeit | undefined {
  return faelligkeiten
    ?.filter(f => f.einheit_id === einheitId)
    .sort((a, b) => a.faellig_am.localeCompare(b.faellig_am))[0]
}
