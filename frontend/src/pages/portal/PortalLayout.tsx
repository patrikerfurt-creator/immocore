import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { abmelden, getPortalToken, sepaMandatStatus } from '../../api/portal'
import { Button } from '../../components/ui/Button'
import { SepaMandatDialog } from './SepaMandatDialog'

/**
 * Rahmen des Eigentümer-Portals.
 *
 * Bewusst ohne die interne Sidebar: das Portal ist eine eigene Anwendung
 * für Eigentümer, nicht ein weiterer Menüpunkt der Verwaltungsoberfläche.
 *
 * Kopfzeile und Farben folgen dem abgenommenen Mockup
 * (docs/immocore_portal_mockup.html); die Navigation "Meine Einheiten /
 * Meine Daten" bleibt erhalten — das Mockup zeigt nur die Einheiten-Ansicht,
 * die Eigene-Daten-Seite aus Spec 1a darf dadurch nicht wegfallen.
 */
export function PortalLayout() {
  const navigate = useNavigate()
  const [dialogOffen, setDialogOffen] = useState(false)
  const angemeldet = Boolean(getPortalToken())

  // Nur mit Sitzung abfragen; ohne Token leitet das Layout ohnehin zur Anmeldung um.
  const sepaStatus = useQuery({
    queryKey: ['portal', 'sepa-mandat'],
    queryFn: sepaMandatStatus,
    enabled: angemeldet,
  })

  if (!angemeldet) {
    return <Navigate to="/portal/login" replace />
  }

  async function handleAbmelden() {
    await abmelden()
    navigate('/portal/login', { replace: true })
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 text-[13.5px] font-semibold rounded-lg transition-colors ${
      isActive
        ? 'bg-portal-brand-soft text-portal-brand'
        : 'text-portal-soft hover:text-portal-ink'
    }`

  // Während des Ladens und bei Fehlern bleibt der Button mit neutralem Label stehen.
  const sepaLabel =
    sepaStatus.data?.kopfzeile_aktion === 'aendern'
      ? 'SEPA-Lastschriftmandat ändern'
      : 'SEPA-Lastschriftmandat'

  function handleSepaKlick() {
    if (!sepaStatus.data) sepaStatus.refetch()
    setDialogOffen(true)
  }

  return (
    <div className="min-h-screen bg-portal-paper text-portal-ink">
      <div className="max-w-[960px] mx-auto px-5">
        <header className="flex items-center justify-between gap-4 pt-[22px] pb-[18px] border-b border-portal-line">
          <div className="flex items-center gap-2.5">
            <div className="w-[30px] h-[30px] rounded-lg bg-portal-brand text-white text-sm font-bold flex items-center justify-center">
              IC
            </div>
            <div>
              <div className="font-bold tracking-[0.2px] leading-tight">IMMOCORE Portal</div>
              <div className="text-xs text-portal-soft">Demme Immobilien Verwaltung GmbH</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <nav className="flex gap-1">
              <NavLink to="/portal/einheiten" className={linkClass}>Meine Einheiten</NavLink>
              <NavLink to="/portal/daten" className={linkClass}>Meine Daten</NavLink>
            </nav>
            <Button type="button" variant="portal-secondary" size="sm" onClick={handleSepaKlick}>
              {sepaLabel}
            </Button>
            <button
              onClick={handleAbmelden}
              className="text-[13px] text-portal-soft hover:text-portal-ink underline"
            >
              Abmelden
            </button>
          </div>
        </header>

        <main className="pb-[60px]">
          <Outlet />
        </main>
      </div>

      {dialogOffen && sepaStatus.data && (
        <SepaMandatDialog status={sepaStatus.data} onClose={() => setDialogOffen(false)} />
      )}
    </div>
  )
}
