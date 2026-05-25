import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../stores/auth'
import { useObjektStore } from '../stores/objekt'
import { objekteApi } from '../api/objekte'

type NavItemDef = { to: string; label: string; icon: string; objektAware?: boolean }

const stammdatenItems: NavItemDef[] = [
  { to: '/objekte',                        label: 'Objekte',            icon: '🏢' },
  { to: '/personen',                       label: 'Personen',           icon: '👤' },
  { to: '/einheiten',                      label: 'Einheiten',          icon: '🏠' },
  { to: '/vertragsmanagement',             label: 'Vertragsmanagement', icon: '📋' },
  { to: '/stammdaten/abrechnungsarten',    label: 'Abrechnungsarten',   icon: '📊', objektAware: true },
  { to: '/stammdaten/verteilerschluessel', label: 'Verteilerschlüssel', icon: '🔑', objektAware: true },
  { to: '/stammdaten/kontenplan',          label: 'Kontenplan',         icon: '📈', objektAware: true },
]

const buchhaltungItems: NavItemDef[] = [
  { to: '/kreditoren',                 label: 'Kreditoren',        icon: '🏭' },
  { to: '/buchhaltung/debitoren',      label: 'Debitoren',         icon: '👥', objektAware: true },
  { to: '/buchhaltung/dialog',         label: 'Dialogbuchhaltung', icon: '✏️', objektAware: true },
  { to: '/buchhaltung/sollstellungen', label: 'Sollstellung',      icon: '📬', objektAware: true },
  { to: '/buchhaltung/auto-pipeline', label: 'Auto-Pipeline',     icon: '🤖' },
  { to: '/buchhaltung/kontoauszug',    label: 'Kontoauszug',       icon: '📋', objektAware: true },
  { to: '/buchhaltung/ebanking',       label: 'E-Banking',         icon: '🏦', objektAware: true },
  { to: '/buchhaltung/wkz-vorlagen',   label: 'WKZ',               icon: '🔁', objektAware: true },
  { to: '/rechnungen',                        label: 'Rechnungen',        icon: '🧾', objektAware: true },
  { to: '/admin/rechnungen/match-regeln',     label: 'Match-Regeln',      icon: '🔗' },
  { to: '/buchhaltung',                       label: 'Buchungsjournal',   icon: '📒', objektAware: true },
]

const zahlungsverkehrItems: NavItemDef[] = [
  { to: '/zahlungsverkehr/lastschrift', label: 'Lastschrift',    icon: '🔄', objektAware: true },
  { to: '/zahlungsverkehr/zahlungen',   label: 'Zahlungen',      icon: '💸', objektAware: true },
]

const abrechnungWpItems: NavItemDef[] = [
  { to: '/abrechnung-wp/wirtschaftsplan', label: 'Wirtschaftsplan', icon: '📋', objektAware: true },
]

const otherItems: NavItemDef[] = [
  { to: '/prozesse',        label: 'Prozesse',    icon: '⚙️' },
  { to: '/dokumente',       label: 'Dokumente',   icon: '📁', objektAware: true },
  { to: '/tickets',         label: 'Tickets',     icon: '🎫', objektAware: true },
  { to: '/massenimport/weg', label: 'Massenimport', icon: '📥' },
  { to: '/mitarbeiter',     label: 'Mitarbeiter', icon: '👥' },
]

const stammdatenPaths = stammdatenItems.map(i => i.to)
const buchhaltungPaths = [...buchhaltungItems.map(i => i.to), '/rechnungen', '/buchhaltung/wkz-ops']
const zahlungsverkehrPaths = zahlungsverkehrItems.map(i => i.to)
const abrechnungWpPaths = abrechnungWpItems.map(i => i.to)

function resolvedTo(item: NavItemDef, selectedId: string | null) {
  if (item.objektAware && selectedId) {
    return { pathname: item.to, search: `?objekt=${selectedId}` }
  }
  return item.to
}

function SidebarLink({ item, selectedId, indent = false }: { item: NavItemDef; selectedId: string | null; indent?: boolean }) {
  const isEnd = item.to === '/' || item.to === '/buchhaltung'
  return (
    <NavLink
      to={resolvedTo(item, selectedId)}
      end={isEnd}
      className={({ isActive }) =>
        `flex items-center gap-3 ${indent ? 'pl-9 pr-5' : 'px-5'} py-2.5 text-sm transition-colors ${
          isActive
            ? 'bg-primary-700 text-white font-medium'
            : 'text-primary-200 hover:bg-primary-800 hover:text-white'
        }`
      }
    >
      <span className="text-base">{item.icon}</span>
      {item.label}
    </NavLink>
  )
}

function ObjektSelector() {
  const { selectedId, setSelected, clearSelected } = useObjektStore()
  const { data: objekte } = useQuery({
    queryKey: ['objekte-sidebar'],
    queryFn: objekteApi.list,
  })

  return (
    <div className="px-3 py-2 border-b border-primary-800">
      <div className="text-xs text-primary-500 mb-1 px-1">Objekt</div>
      <div className="flex items-center gap-1">
        <select
          value={selectedId ?? ''}
          onChange={(e) => {
            const obj = objekte?.find(o => o.id === e.target.value)
            if (obj) setSelected(obj.id, obj.bezeichnung, obj.objektnummer, obj.objekt_typ)
            else clearSelected()
          }}
          className="flex-1 min-w-0 bg-primary-800 text-primary-100 text-xs rounded px-2 py-1.5 border border-primary-700 cursor-pointer hover:bg-primary-700 focus:outline-none focus:border-primary-500"
        >
          <option value="">— wählen —</option>
          {objekte?.map(o => (
            <option key={o.id} value={o.id}>{o.objektnummer} {o.bezeichnung}</option>
          ))}
        </select>
        {selectedId && (
          <button
            onClick={clearSelected}
            className="text-primary-500 hover:text-white text-xs flex-shrink-0 px-1"
            title="Auswahl aufheben"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}

export function Sidebar() {
  const { username, logout, istFrontoffice, ladeGruppen } = useAuthStore()
  const location = useLocation()

  useEffect(() => { ladeGruppen() }, [])

  const isInStammdaten = stammdatenPaths.some(p => location.pathname.startsWith(p))
  const isInBuchhaltung = buchhaltungPaths.some(p => location.pathname.startsWith(p))
  const isInZahlungsverkehr = zahlungsverkehrPaths.some(p => location.pathname.startsWith(p))
  const isInAbrechnungWp = abrechnungWpPaths.some(p => location.pathname.startsWith(p))

  const [stammdatenOpen, setStammdatenOpen] = useState(isInStammdaten)
  const [buchhaltungOpen, setBuchhaltungOpen] = useState(isInBuchhaltung)
  const [zahlungsverkehrOpen, setZahlungsverkehrOpen] = useState(isInZahlungsverkehr)
  const [abrechnungWpOpen, setAbrechnungWpOpen] = useState(isInAbrechnungWp)

  const { selectedId } = useObjektStore()

  return (
    <aside className="flex flex-col w-56 h-screen sticky top-0 bg-primary-900 text-white">
      <div className="px-5 py-4 border-b border-primary-700 flex-shrink-0">
        <span className="text-lg font-bold tracking-wide">IMMOCORE</span>
      </div>

      <nav className="flex-1 py-3 overflow-y-auto">
        <SidebarLink item={{ to: '/', label: 'Dashboard', icon: '⊞' }} selectedId={selectedId} />

        <ObjektSelector />

        <div>
          <button
            onClick={() => setStammdatenOpen(o => !o)}
            className={`w-full flex items-center justify-between px-5 py-2.5 text-sm transition-colors ${
              isInStammdaten
                ? 'text-white font-medium'
                : 'text-primary-200 hover:bg-primary-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-3">
              <span className="text-base">🗂️</span>
              Stammdaten
            </span>
            <span className="text-xs text-primary-400">{stammdatenOpen ? '▲' : '▼'}</span>
          </button>

          {stammdatenOpen && (
            <div>
              {stammdatenItems.map(item => (
                <SidebarLink key={item.to} item={item} selectedId={selectedId} indent />
              ))}
            </div>
          )}
        </div>

        <div>
          <button
            onClick={() => setBuchhaltungOpen(o => !o)}
            className={`w-full flex items-center justify-between px-5 py-2.5 text-sm transition-colors ${
              isInBuchhaltung
                ? 'text-white font-medium'
                : 'text-primary-200 hover:bg-primary-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-3">
              <span className="text-base">💰</span>
              Buchhaltung
            </span>
            <span className="text-xs text-primary-400">{buchhaltungOpen ? '▲' : '▼'}</span>
          </button>

          {buchhaltungOpen && (
            <div>
              {buchhaltungItems.map(item => (
                <SidebarLink key={item.to} item={item} selectedId={selectedId} indent />
              ))}
              {istFrontoffice && (
                <SidebarLink
                  item={{ to: '/rechnungen/frontoffice', label: 'Frontoffice-Inbox', icon: '📥' }}
                  selectedId={selectedId}
                  indent
                />
              )}
            </div>
          )}
        </div>

        <div>
          <button
            onClick={() => setZahlungsverkehrOpen(o => !o)}
            className={`w-full flex items-center justify-between px-5 py-2.5 text-sm transition-colors ${
              isInZahlungsverkehr
                ? 'text-white font-medium'
                : 'text-primary-200 hover:bg-primary-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-3">
              <span className="text-base">🏧</span>
              Zahlungsverkehr
            </span>
            <span className="text-xs text-primary-400">{zahlungsverkehrOpen ? '▲' : '▼'}</span>
          </button>

          {zahlungsverkehrOpen && (
            <div>
              {zahlungsverkehrItems.map(item => (
                <SidebarLink key={item.to} item={item} selectedId={selectedId} indent />
              ))}
            </div>
          )}
        </div>

        <div>
          <button
            onClick={() => setAbrechnungWpOpen(o => !o)}
            className={`w-full flex items-center justify-between px-5 py-2.5 text-sm transition-colors ${
              isInAbrechnungWp
                ? 'text-white font-medium'
                : 'text-primary-200 hover:bg-primary-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-3">
              <span className="text-base">📊</span>
              Abrechnung & WP
            </span>
            <span className="text-xs text-primary-400">{abrechnungWpOpen ? '▲' : '▼'}</span>
          </button>
          {abrechnungWpOpen && (
            <div>
              {abrechnungWpItems.map(item => (
                <SidebarLink key={item.to} item={item} selectedId={selectedId} indent />
              ))}
            </div>
          )}
        </div>

        {otherItems.map(item => (
          <SidebarLink key={item.to} item={item} selectedId={selectedId} />
        ))}
      </nav>

      <div className="px-5 py-4 border-t border-primary-700 text-xs text-primary-300 flex-shrink-0">
        <p className="mb-2 truncate">{username}</p>
        <div className="flex flex-col gap-1.5">
          <NavLink
            to="/einstellungen"
            className={({ isActive }) =>
              `transition-colors ${isActive ? 'text-white font-medium' : 'text-primary-300 hover:text-white'}`
            }
          >
            ⚙ Einstellungen
          </NavLink>
          <button
            onClick={logout}
            className="text-left text-primary-300 hover:text-white transition-colors"
          >
            Abmelden
          </button>
        </div>
      </div>
    </aside>
  )
}
