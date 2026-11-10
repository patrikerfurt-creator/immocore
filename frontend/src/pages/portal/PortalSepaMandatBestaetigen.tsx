import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getPortalToken,
  sepaMandatBestaetigen,
  sepaMandatVorschau,
  type SepaMandatBestaetigenAntwort,
  type SepaMandatVorschau,
} from '../../api/portal'
import { Button } from '../../components/ui/Button'
import { formatDatumZeit, titelFuerAktion } from './SepaMandatDialog'

/**
 * Bestätigungsseite für das SEPA-Lastschriftmandat (Architekturentscheid b).
 *
 * Bewusst KEIN automatisches Bestätigen beim Laden: Mail-Scanner (Safe Links)
 * rufen Links samt JavaScript ab. Beim Laden wird nur die Vorschau geholt
 * (verbraucht den Link nicht); die Zustimmung ist der POST nach Klick auf
 * den Button mit gesetzter Checkbox.
 *
 * Ohne Anmeldezwang — der Link wird oft in einem Browser ohne Portal-Sitzung geöffnet.
 */
function fehlertext(fehler: unknown): string {
  const detail = (fehler as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail ?? 'Das Mandat konnte nicht bestätigt werden. Bitte versuchen Sie es erneut.'
}

export function PortalSepaMandatBestaetigen() {
  const { token } = useParams<{ token: string }>()
  const bereitsGeladen = useRef(false)
  const [zustand, setZustand] = useState<'laedt' | 'bereit' | 'fehler'>('laedt')
  const [vorschau, setVorschau] = useState<SepaMandatVorschau | null>(null)
  const [erklaerung, setErklaerung] = useState(false)
  const [sendet, setSendet] = useState(false)
  const [fehler, setFehler] = useState('')
  const [ergebnis, setErgebnis] = useState<SepaMandatBestaetigenAntwort | null>(null)

  useEffect(() => {
    if (!token || bereitsGeladen.current) return
    bereitsGeladen.current = true

    sepaMandatVorschau(token)
      .then((daten) => {
        setVorschau(daten)
        setZustand('bereit')
      })
      .catch(() => setZustand('fehler'))
  }, [token])

  async function handleBestaetigen() {
    if (!token || !erklaerung || sendet) return
    setSendet(true)
    setFehler('')
    try {
      setErgebnis(await sepaMandatBestaetigen(token, true))
    } catch (e) {
      setFehler(fehlertext(e))
    } finally {
      setSendet(false)
    }
  }

  const angemeldet = Boolean(getPortalToken())
  const zurueck = (
    <Link to={angemeldet ? '/portal/daten' : '/portal/login'} className="text-sm text-portal-brand hover:underline">
      {angemeldet ? 'Zurück zu meinen Daten' : 'Zur Anmeldung'}
    </Link>
  )

  return (
    <div className="min-h-screen bg-portal-brand flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-xl bg-white rounded-xl shadow-xl p-8 text-portal-ink">
        {zustand === 'laedt' && (
          <>
            <h1 className="text-2xl font-bold text-portal-brand mb-4 text-center">SEPA-Lastschriftmandat</h1>
            <p className="text-sm text-portal-soft text-center">Wird geladen…</p>
          </>
        )}

        {zustand === 'fehler' && (
          <div className="text-center">
            <h1 className="text-2xl font-bold text-portal-brand mb-4">SEPA-Lastschriftmandat</h1>
            <p className="text-sm text-portal-debit mb-4">
              Dieser Link ist ungültig oder abgelaufen. Bitte fordern Sie das Mandat im Portal erneut an.
            </p>
            {zurueck}
          </div>
        )}

        {zustand === 'bereit' && vorschau && ergebnis && (
          <div className="text-center">
            <h1 className="text-2xl font-bold text-portal-brand mb-4">
              {ergebnis.aktion === 'aendern' ? 'Mandat geändert' : 'Mandat erteilt'}
            </h1>
            <p className="text-sm text-portal-credit mb-3">{ergebnis.detail}</p>
            <p className="text-sm mb-1">Mandatsreferenz: <strong>{ergebnis.mandatsreferenz}</strong></p>
            <p className="text-sm mb-3">{ergebnis.geltungsbereich_text}</p>
            <p className="text-sm text-portal-soft mb-4">
              Eine Kopie des Mandats haben wir Ihnen per E-Mail gesendet.
            </p>
            {zurueck}
          </div>
        )}

        {zustand === 'bereit' && vorschau && !ergebnis && (
          <div className="flex flex-col gap-4">
            <h1 className="text-2xl font-bold text-portal-brand">{titelFuerAktion(vorschau.aktion)}</h1>

            <p className="text-sm font-medium">{vorschau.geltungsbereich_text}</p>
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-portal-soft">Kontoinhaber</dt>
              <dd>{vorschau.kontoinhaber_name}</dd>
              <dt className="text-portal-soft">IBAN</dt>
              <dd className="font-mono">{vorschau.iban_maskiert}</dd>
              <dt className="text-portal-soft">BIC</dt>
              <dd className="font-mono">{vorschau.bic || '—'}</dd>
              <dt className="text-portal-soft">Mandatsreferenz</dt>
              <dd className="font-mono">{vorschau.mandatsreferenz}</dd>
            </dl>

            <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed max-h-72 overflow-y-auto border border-portal-line bg-portal-paper rounded p-3">
              {vorschau.mandatstext}
            </pre>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={erklaerung}
                onChange={(e) => setErklaerung(e.target.checked)}
              />
              <span>
                Ich bin Inhaber des angegebenen Kontos und erteile dieses SEPA-Lastschriftmandat verbindlich.
              </span>
            </label>

            {fehler && <p role="alert" className="text-sm text-portal-debit">{fehler}</p>}

            <div>
              <Button type="button" variant="portal" disabled={!erklaerung || sendet} onClick={handleBestaetigen}>
                {sendet
                  ? 'Wird gesendet…'
                  : vorschau.aktion === 'aendern' ? 'Änderung verbindlich bestätigen' : 'Mandat verbindlich erteilen'}
              </Button>
              <p className="text-xs text-portal-soft mt-2">Gültig bis {formatDatumZeit(vorschau.gueltig_bis)}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
