import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { tokenEinloesen } from '../../api/portal'

/**
 * Löst den Link aus der E-Mail ein (Einladung wie Magic Link, Spec Kap. 3).
 *
 * Der Token ist einmalig — deshalb verhindert ``bereitsGesendet``, dass
 * Reacts StrictMode den Aufruf im Entwicklungsmodus doppelt absetzt und
 * der zweite Aufruf den gerade eröffneten Zugang als "ungültig" meldet.
 */
export function PortalAnmelden() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const bereitsGesendet = useRef(false)
  const [fehler, setFehler] = useState('')

  useEffect(() => {
    if (!token || bereitsGesendet.current) return
    bereitsGesendet.current = true

    tokenEinloesen(token)
      .then(() => navigate('/portal/einheiten', { replace: true }))
      .catch(() => setFehler(
        'Dieser Link ist ungültig oder abgelaufen. Fordern Sie bitte einen neuen Anmeldelink an.',
      ))
  }, [token, navigate])

  return (
    <div className="min-h-screen bg-primary-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-xl p-8 text-center">
        <h1 className="text-2xl font-bold text-primary-900 mb-4">Eigentümer-Portal</h1>
        {fehler ? (
          <>
            <p className="text-sm text-red-600 mb-4">{fehler}</p>
            <button
              onClick={() => navigate('/portal/login', { replace: true })}
              className="text-sm text-primary-700 hover:underline"
            >
              Zur Anmeldung
            </button>
          </>
        ) : (
          <p className="text-sm text-gray-600">Sie werden angemeldet…</p>
        )}
      </div>
    </div>
  )
}
