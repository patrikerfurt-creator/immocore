import { Navigate, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { abmelden, getPortalToken } from '../../api/portal'

/**
 * Rahmen des Eigentümer-Portals.
 *
 * Bewusst ohne die interne Sidebar: das Portal ist eine eigene Anwendung
 * für Eigentümer, nicht ein weiterer Menüpunkt der Verwaltungsoberfläche.
 */
export function PortalLayout() {
  const navigate = useNavigate()

  if (!getPortalToken()) {
    return <Navigate to="/portal/login" replace />
  }

  async function handleAbmelden() {
    await abmelden()
    navigate('/portal/login', { replace: true })
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 text-sm font-medium rounded transition-colors ${
      isActive ? 'bg-primary-100 text-primary-900' : 'text-gray-600 hover:bg-gray-100'
    }`

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div>
            <p className="text-lg font-bold text-primary-900 leading-tight">Eigentümer-Portal</p>
            <p className="text-xs text-gray-500">Demme Immobilien Verwaltung GmbH</p>
          </div>
          <button
            onClick={handleAbmelden}
            className="text-sm text-gray-500 hover:text-gray-800 underline"
          >
            Abmelden
          </button>
        </div>
        <nav className="max-w-4xl mx-auto px-4 pb-2 flex gap-1">
          <NavLink to="/portal/einheiten" className={linkClass}>Meine Einheiten</NavLink>
          <NavLink to="/portal/daten" className={linkClass}>Meine Daten</NavLink>
        </nav>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
