import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { meineEinheiten, PortalEinheit, PortalWegKarte } from '../../api/portal'

/**
 * Einheiten-Ansicht im Button-Layout (Layout-Update v1.0).
 *
 * Optik und Verhalten 1:1 aus dem abgenommenen Mockup
 * (docs/immocore_portal_mockup.html): WEG-Buttons (aktiv = Markengrün) →
 * Einheiten-Tabs (aktiv = Ink) → Saldo-Karten → Reiter Konto/Dokumente/
 * Vorgänge, wobei jeder Wechsel von WEG oder Einheit auf "Konto" zurückspringt.
 *
 * Inhaltlich weiterhin nur Stammdaten je Einheit (Spec 1a, Kap. 6.1).
 * Personenkonto (Saldo, Buchungsverlauf), Dokumente und Vorgänge folgen in
 * Spec 1 (vollständig) — ihre Flächen stehen hier bereits im Layout, aber mit
 * Platzhalter statt erfundener Zahlen.
 */
const NUTZUNGSART_LABEL: Record<string, string> = {
  Wohnung: 'Wohnung',
  Gewerbe: 'Gewerbeeinheit',
  Stellplatz: 'Stellplatz',
  Sonstiges: 'Sonstiges',
}

type ReiterId = 'konto' | 'dokumente' | 'vorgaenge'

const REITER: { id: ReiterId; label: string }[] = [
  { id: 'konto', label: 'Konto' },
  { id: 'dokumente', label: 'Dokumente' },
  { id: 'vorgaenge', label: 'Vorgänge' },
]

function formatMea(wert: string | null): string {
  if (wert === null) return '—'
  // Der MEA kommt als Dezimalstring mit vier Nachkommastellen; nachlaufende
  // Nullen wegzulassen macht ihn lesbarer, ohne den Wert zu verändern.
  const zahl = Number(wert)
  if (Number.isNaN(zahl)) return wert
  return zahl.toLocaleString('de-DE', { maximumFractionDigits: 4 })
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-portal-soft mt-6 mb-2.5">
      {children}
    </p>
  )
}

/** Saldo-Karte aus dem Mockup — Werte folgen mit Spec 1b (Personenkonto). */
function KennzahlKarte({ label, wert, hinweis }: { label: string; wert: string; hinweis: string }) {
  return (
    <div className="flex-1 basis-[200px] bg-white border border-portal-line rounded-[10px] px-[18px] py-4">
      <div className="text-xs text-portal-soft mb-1.5">{label}</div>
      <div className="text-base font-semibold text-portal-soft">{wert}</div>
      <div className="text-[11.5px] text-portal-soft mt-1">{hinweis}</div>
    </div>
  )
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
    <dl className="mt-4 bg-white border border-portal-line rounded-[10px] px-[18px] py-2">
      {zeilen.map(([label, wert], i) => (
        <div
          key={label}
          className={`flex justify-between gap-4 py-2.5 ${
            i < zeilen.length - 1 ? 'border-b border-portal-line' : ''
          }`}
        >
          <dt className="text-[13.5px] text-portal-soft">{label}</dt>
          <dd className="text-[13.5px] font-medium text-portal-ink text-right">{wert}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Gestrichelte Platzhalterfläche aus dem Mockup (.placeholder). */
function Platzhalter({ text }: { text: string }) {
  return (
    <div className="mt-[18px] px-6 py-[26px] text-center text-[13.5px] text-portal-soft bg-white border border-dashed border-portal-line rounded-[10px]">
      {text}
    </div>
  )
}

export function MeineEinheiten() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['portal', 'einheiten'],
    queryFn: meineEinheiten,
  })

  // Auswahl über IDs statt Indizes: so bleibt die Auswahl stabil, wenn der
  // Server die Liste in anderer Reihenfolge liefert. `null` heißt "noch nichts
  // gewählt" und fällt im Render auf den ersten Eintrag zurück.
  const [wegId, setWegId] = useState<string | null>(null)
  const [einheitId, setEinheitId] = useState<string | null>(null)
  const [reiter, setReiter] = useState<ReiterId>('konto')

  if (isLoading) return <p className="text-sm text-portal-soft">Wird geladen…</p>
  if (isError) {
    return <p className="text-sm text-portal-debit">Die Daten konnten nicht geladen werden.</p>
  }

  if (!data?.length) {
    return (
      <div className="bg-white border border-portal-line rounded-[10px] p-6">
        <p className="text-sm text-portal-soft">
          Zu Ihrem Zugang sind derzeit keine Einheiten hinterlegt. Bitte wenden Sie sich
          an Ihre Hausverwaltung.
        </p>
      </div>
    )
  }

  const weg: PortalWegKarte = data.find(w => w.objekt_id === wegId) ?? data[0]
  // Nach einem WEG-Wechsel zeigt `einheitId` unter Umständen noch auf die alte
  // WEG; der Fallback greift dann die erste Einheit der neuen WEG.
  const einheit = weg.einheiten.find(e => e.einheit_id === einheitId) ?? weg.einheiten[0]

  function wegWaehlen(gewaehlt: PortalWegKarte) {
    setWegId(gewaehlt.objekt_id)
    setEinheitId(gewaehlt.einheiten[0]?.einheit_id ?? null)
    // WEG-Wechsel springt zurück auf "Konto" — ein offener Dokumente- oder
    // Vorgänge-Reiter bezöge sich sonst plötzlich auf eine andere Einheit.
    setReiter('konto')
  }

  function einheitWaehlen(gewaehlt: PortalEinheit) {
    setEinheitId(gewaehlt.einheit_id)
    setReiter('konto')
  }

  const einheitenLabel = weg.einheiten.length > 1
    ? `Ihre Einheiten in ${weg.bezeichnung} (${weg.einheiten.length})`
    : `Ihre Einheit in ${weg.bezeichnung}`

  return (
    <div>
      {/* Ebene 1: WEG-Auswahl — eine Reihe, bei vielen WEGs umbrechend. */}
      <SectionLabel>
        {data.length > 1 ? `Ihre WEGs (${data.length})` : 'Ihre WEG'}
      </SectionLabel>
      <div className="flex flex-wrap gap-2">
        {data.map(karte => {
          const aktiv = karte.objekt_id === weg.objekt_id
          return (
            <button
              key={karte.objekt_id}
              onClick={() => wegWaehlen(karte)}
              aria-pressed={aktiv}
              className={`px-[18px] py-[11px] rounded-lg border text-sm font-semibold transition-colors ${
                aktiv
                  ? 'bg-portal-brand border-portal-brand text-white'
                  : 'bg-white border-portal-line text-portal-ink hover:border-[#c7cdd6]'
              }`}
            >
              {karte.bezeichnung}
            </button>
          )
        })}
      </div>

      {/* Ebene 2: Einheiten-Auswahl — auch bei nur einer Einheit sichtbar. */}
      <SectionLabel>{einheitenLabel}</SectionLabel>
      <p className="-mt-1.5 mb-2.5 text-xs text-portal-soft">
        {weg.strasse}, {weg.plz} {weg.ort}
      </p>
      {weg.einheiten.length ? (
        <div className="flex flex-wrap gap-1.5">
          {weg.einheiten.map(e => {
            const aktiv = e.einheit_id === einheit?.einheit_id
            return (
              <button
                key={e.einheit_id}
                onClick={() => einheitWaehlen(e)}
                aria-pressed={aktiv}
                className={`px-3.5 py-2 rounded-lg border text-[13.5px] font-medium transition-colors ${
                  aktiv
                    ? 'bg-portal-ink border-portal-ink text-white'
                    : 'bg-white border-portal-line text-portal-soft hover:border-[#c7cdd6]'
                }`}
              >
                {e.einheit_nr}
              </button>
            )
          })}
        </div>
      ) : (
        <p className="text-[13.5px] text-portal-soft">Keine Einheiten hinterlegt.</p>
      )}

      {/* Ebene 3: Kennzahlen + Reiter — erst wenn eine Einheit ausgewählt ist. */}
      {einheit && (
        <>
          <div className="flex flex-wrap gap-3.5 mt-[18px]">
            <KennzahlKarte
              label={`Aktueller Saldo — ${einheit.einheit_nr}`}
              wert="wird in Kürze angezeigt"
              hinweis="Personenkonto in Vorbereitung"
            />
            <KennzahlKarte
              label="Nächste Fälligkeit"
              wert="wird in Kürze angezeigt"
              hinweis="Hausgeld / Sollstellung"
            />
          </div>

          <div className="flex gap-[22px] mt-7 border-b border-portal-line">
            {REITER.map(({ id, label }) => (
              <button
                key={id}
                onClick={() => setReiter(id)}
                aria-current={id === reiter ? 'page' : undefined}
                className={`pb-2.5 -mb-px text-[13.5px] font-semibold border-b-2 transition-colors ${
                  id === reiter
                    ? 'text-portal-ink border-portal-brand'
                    : 'text-portal-soft border-transparent hover:text-portal-ink'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {reiter === 'konto' && (
            <>
              <EinheitDetails einheit={einheit} />
              <Platzhalter text="Ihr Kontostand und der Buchungsverlauf zu dieser Einheit erscheinen hier." />
            </>
          )}
          {reiter === 'dokumente' && (
            <Platzhalter text="Dokumente zu dieser Einheit erscheinen hier." />
          )}
          {reiter === 'vorgaenge' && (
            <Platzhalter text="Vorgänge zu dieser Einheit erscheinen hier." />
          )}
        </>
      )}

      <div className="mt-[22px] bg-white border border-portal-line rounded-[10px] px-3.5 py-3 text-xs text-portal-soft">
        Diese Ansicht zeigt ausschließlich Ihre eigenen Einheiten — serverseitig
        gefiltert auf Ihre Person, unabhängig davon, wie viele WEGs oder Einheiten Sie
        besitzen. Andere Eigentümer sind für Sie nicht einsehbar.
      </div>
    </div>
  )
}
