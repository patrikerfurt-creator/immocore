import { FormEvent, useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ibanPruefen,
  istSammelbereich,
  sepaMandatAnfordern,
  type SepaGeltungsbereich,
  type SepaGeltungsbereichEinheit,
  type SepaMandatAktion,
  type SepaMandatStatus,
} from '../../api/portal'
import { Button } from '../../components/ui/Button'
import { IbanInput, type IbanCheckResult } from '../../components/ui/IbanInput'
import { Input } from '../../components/ui/Input'

/**
 * Dialog "SEPA-Lastschriftmandat erteilen / ändern" im Eigentümer-Portal.
 *
 * Der Dialog legt nur eine Anfrage an: das Mandat wird erst mit der
 * Bestätigung über den Link in der E-Mail wirksam (siehe
 * PortalSepaMandatBestaetigen). Die IBAN wird serverseitig beim Anfordern
 * erneut verbindlich geprüft.
 */

export function fehlertextAnfordern(fehler: unknown): string {
  const antwort = (fehler as { response?: { status?: number; data?: { detail?: string } } })?.response
  if (antwort?.status === 429) return 'Zu viele Anfragen. Bitte versuchen Sie es später erneut.'
  return antwort?.data?.detail ?? 'Die Anfrage konnte nicht gesendet werden. Bitte versuchen Sie es erneut.'
}

export function formatDatum(wert: string | null | undefined): string {
  if (!wert) return ''
  const d = new Date(wert)
  return Number.isNaN(d.getTime()) ? wert : d.toLocaleDateString('de-DE')
}

export function formatDatumZeit(wert: string | null | undefined): string {
  if (!wert) return ''
  const d = new Date(wert)
  return Number.isNaN(d.getTime())
    ? wert
    : d.toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' })
}

export function titelFuerAktion(aktion: SepaMandatAktion): string {
  return aktion === 'aendern' ? 'SEPA-Lastschriftmandat ändern' : 'SEPA-Lastschriftmandat erteilen'
}

interface Props {
  status: SepaMandatStatus
  onClose: () => void
}

export function SepaMandatDialog({ status, onClose }: Props) {
  const queryClient = useQueryClient()
  const karteRef = useRef<HTMLDivElement>(null)

  const einheiten = status.geltungsbereiche.filter(
    (b): b is SepaGeltungsbereichEinheit => !istSammelbereich(b),
  )
  const [modus, setModus] = useState<'alle' | 'einheit'>('alle')
  const [einheitSchluessel, setEinheitSchluessel] = useState(einheiten[0]?.schluessel ?? '')
  const [iban, setIban] = useState('')
  const [bic, setBic] = useState('')
  // Letztes serverseitiges Prüfergebnis, gebunden an die geprüfte IBAN. IbanInput
  // gibt seinen Status nicht nach außen; ein Prüfergebnis für eine andere IBAN
  // zählt nicht.
  const [geprueft, setGeprueft] = useState<{ iban: string; valid: boolean } | null>(null)
  const [erfolgAktion, setErfolgAktion] = useState<SepaMandatAktion | null>(null)

  const schluessel = status.auswahl_noetig
    ? (modus === 'alle' ? 'alle' : einheitSchluessel)
    : (status.geltungsbereiche[0]?.schluessel ?? '')
  const gewaehlt: SepaGeltungsbereich | undefined = status.geltungsbereiche.find(
    (b) => b.schluessel === schluessel,
  )
  const aktion: SepaMandatAktion = gewaehlt?.aktion ?? status.kopfzeile_aktion

  const offen = status.offene_anfrage
  const offenerBereich = offen
    ? status.geltungsbereiche.find((b) => b.schluessel === offen.schluessel)
    : undefined

  const mutation = useMutation({
    mutationFn: sepaMandatAnfordern,
    onSuccess: () => {
      setErfolgAktion(aktion)
      queryClient.invalidateQueries({ queryKey: ['portal', 'sepa-mandat'] })
    },
  })

  // Esc schliesst; Fokus auf das erste Eingabefeld (bzw. den Schliessen-Button).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    karteRef.current
      ?.querySelector<HTMLElement>('input:not([disabled]), select:not([disabled]), button')
      ?.focus()
  }, [])

  async function pruefeUndMerke(wert: string): Promise<IbanCheckResult> {
    const ergebnis = await ibanPruefen(wert)
    setGeprueft({ iban: wert, valid: ergebnis.valid })
    return ergebnis
  }

  const ibanClean = iban.replace(/\s/g, '').toUpperCase()
  const ibanGueltig = geprueft?.valid === true && geprueft.iban === ibanClean
  const kannSenden = ibanGueltig && Boolean(schluessel) && !mutation.isPending

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!kannSenden) return
    mutation.mutate({ schluessel, iban: ibanClean, ...(bic ? { bic } : {}) })
  }

  const titel = titelFuerAktion(erfolgAktion ?? aktion)

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={karteRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sepa-mandat-titel"
        className="mt-12 bg-white rounded-xl shadow-xl max-w-lg w-full p-6 text-portal-ink"
      >
        <h2 id="sepa-mandat-titel" className="text-lg font-bold text-portal-brand mb-4">
          {titel}
        </h2>

        {!status.kann_erteilen ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-portal-ink">{status.hinderungsgrund}</p>
            <div>
              <Button type="button" variant="portal-secondary" onClick={onClose}>Schließen</Button>
            </div>
          </div>
        ) : mutation.isSuccess ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-portal-credit">{mutation.data.detail}</p>
            <div>
              <Button type="button" variant="portal" onClick={onClose}>Schließen</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {offen && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-3">
                Für {offenerBereich?.bezeichnung ?? 'den gewählten Bereich'} liegt bereits eine Anfrage vor
                {offen.gueltig_bis ? ` (gültig bis ${formatDatumZeit(offen.gueltig_bis)})` : ''}.
                {' '}Bitte prüfen Sie Ihr E-Mail-Postfach. Eine neue Anfrage ersetzt die bisherige.
              </p>
            )}

            {status.auswahl_noetig && (
              <fieldset className="flex flex-col gap-2">
                <legend className="text-sm font-medium text-portal-ink mb-1">Geltungsbereich</legend>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="sepa-geltungsbereich"
                    checked={modus === 'alle'}
                    onChange={() => setModus('alle')}
                  />
                  Für alle meine Einheiten (Sammelmandat)
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="sepa-geltungsbereich"
                    checked={modus === 'einheit'}
                    onChange={() => setModus('einheit')}
                  />
                  Für eine bestimmte Einheit
                </label>
                {modus === 'einheit' && (
                  <select
                    aria-label="Einheit"
                    value={einheitSchluessel}
                    onChange={(e) => setEinheitSchluessel(e.target.value)}
                    className="rounded border border-portal-line px-3 py-2 text-sm"
                  >
                    {einheiten.map((b) => (
                      <option key={b.schluessel} value={b.schluessel}>{b.bezeichnung}</option>
                    ))}
                  </select>
                )}
              </fieldset>
            )}

            {gewaehlt?.mandat && (
              <p className="text-sm text-portal-soft bg-portal-brand-soft border border-portal-line rounded p-3">
                Aktuelles Mandat: {gewaehlt.mandat.mandatsreferenz}, IBAN {gewaehlt.mandat.iban_maskiert},
                {' '}erteilt am {formatDatum(gewaehlt.mandat.unterzeichnet_am)}
              </p>
            )}
            {gewaehlt && !istSammelbereich(gewaehlt) && !gewaehlt.mandat && gewaehlt.wirksam_ueber === 'alle' && (
              <p className="text-sm text-portal-soft bg-portal-brand-soft border border-portal-line rounded p-3">
                Für diese Einheit gilt derzeit Ihr Sammelmandat. Ein eigenes Mandat für die Einheit hat Vorrang.
              </p>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-portal-ink">IBAN</label>
              <IbanInput
                value={iban}
                onChange={setIban}
                pruefe={pruefeUndMerke}
                onBicFound={(gefundeneBic) => setBic(gefundeneBic)}
              />
            </div>
            <Input
              label="BIC (optional)"
              value={bic}
              onChange={(e) => setBic(e.target.value.toUpperCase())}
            />

            <p className="text-xs text-portal-soft">
              Sie erhalten einen Bestätigungslink an {status.empfaenger_email_maskiert ?? 'Ihre E-Mail-Adresse'}.
              {' '}Das Mandat wird erst mit Ihrer Bestätigung über diesen Link wirksam.
            </p>

            {mutation.isError && (
              <p role="alert" className="text-sm text-portal-debit">{fehlertextAnfordern(mutation.error)}</p>
            )}

            <div className="flex gap-2">
              <Button type="submit" variant="portal" disabled={!kannSenden}>
                {mutation.isPending ? 'Wird gesendet…' : 'Bestätigungslink anfordern'}
              </Button>
              <Button type="button" variant="portal-secondary" onClick={onClose}>Abbrechen</Button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
