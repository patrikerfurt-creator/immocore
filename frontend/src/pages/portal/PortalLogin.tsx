import { FormEvent, useState } from 'react'
import { magicLinkAnfordern } from '../../api/portal'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'

/**
 * Anmeldeseite des Portals (Spec 1a, Kap. 3.2).
 *
 * Die Rückmeldung ist immer dieselbe — sie darf nicht verraten, ob zu
 * einer Adresse ein Zugang besteht. Deshalb wird auch ein Fehler beim
 * Absenden nicht als "Adresse unbekannt" dargestellt.
 */
export function PortalLogin() {
  const [email, setEmail] = useState('')
  const [gesendet, setGesendet] = useState(false)
  const [laedt, setLaedt] = useState(false)
  const [fehler, setFehler] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFehler('')
    setLaedt(true)
    try {
      await magicLinkAnfordern(email)
      setGesendet(true)
    } catch {
      setFehler('Die Anfrage konnte nicht gesendet werden. Bitte versuchen Sie es später erneut.')
    } finally {
      setLaedt(false)
    }
  }

  return (
    <div className="min-h-screen bg-primary-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-xl p-8">
        <h1 className="text-2xl font-bold text-primary-900 mb-1">Eigentümer-Portal</h1>
        <p className="text-sm text-gray-500 mb-6">Demme Immobilien Verwaltung GmbH</p>

        {gesendet ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-gray-700">
              Falls ein Zugang besteht, wurde eine E-Mail versendet. Bitte öffnen Sie
              den Anmeldelink darin — er ist 15 Minuten gültig.
            </p>
            <button
              onClick={() => { setGesendet(false); setEmail('') }}
              className="text-sm text-primary-700 hover:underline text-left"
            >
              Andere E-Mail-Adresse verwenden
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <p className="text-sm text-gray-600">
              Geben Sie Ihre E-Mail-Adresse ein. Sie erhalten einen Anmeldelink —
              ein Passwort brauchen Sie nicht.
            </p>
            <Input
              label="E-Mail-Adresse"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoFocus
              required
            />
            {fehler && <p className="text-sm text-red-600">{fehler}</p>}
            <Button type="submit" disabled={laedt} className="mt-2">
              {laedt ? 'Wird gesendet…' : 'Anmeldelink anfordern'}
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}
