import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { emailBestaetigen, getPortalToken } from '../../api/portal'

/**
 * Bestätigung der neuen E-Mail-Adresse (Spec 1a, Kap. 5.3).
 *
 * Bewusst ohne Anmeldezwang: der Link wird typischerweise im neuen
 * Postfach geöffnet, oft in einem anderen Browser ohne Portal-Sitzung.
 */
export function PortalEmailBestaetigen() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const bereitsGesendet = useRef(false)
  const [zustand, setZustand] = useState<'laedt' | 'ok' | 'fehler'>('laedt')
  const [meldung, setMeldung] = useState('')

  useEffect(() => {
    if (!token || bereitsGesendet.current) return
    bereitsGesendet.current = true

    emailBestaetigen(token)
      .then((antwort) => {
        setZustand('ok')
        setMeldung(`Ihre neue E-Mail-Adresse ${antwort.email} ist jetzt aktiv.`)
      })
      .catch(() => {
        setZustand('fehler')
        setMeldung('Dieser Link ist ungültig oder abgelaufen. Bitte stoßen Sie die Änderung im Portal erneut an.')
      })
  }, [token])

  const angemeldet = Boolean(getPortalToken())

  return (
    <div className="min-h-screen bg-primary-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-xl p-8 text-center">
        <h1 className="text-2xl font-bold text-primary-900 mb-4">E-Mail-Adresse bestätigen</h1>

        {zustand === 'laedt' && <p className="text-sm text-gray-600">Wird geprüft…</p>}
        {zustand === 'ok' && <p className="text-sm text-green-700 mb-4">{meldung}</p>}
        {zustand === 'fehler' && <p className="text-sm text-red-600 mb-4">{meldung}</p>}

        {zustand !== 'laedt' && (
          <button
            onClick={() => navigate(angemeldet ? '/portal/daten' : '/portal/login', { replace: true })}
            className="text-sm text-primary-700 hover:underline"
          >
            {angemeldet ? 'Zurück zu meinen Daten' : 'Zur Anmeldung'}
          </button>
        )}
      </div>
    </div>
  )
}
