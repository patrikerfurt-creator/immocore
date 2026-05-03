import { Outlet, Link } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useObjektStore } from '../stores/objekt'

export function Layout() {
  const { selectedId, selectedName, selectedNummer, selectedTyp, clearSelected } = useObjektStore()

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedId && (
          <div className="bg-white border-b border-gray-200 px-6 py-2 flex items-center gap-3 flex-shrink-0">
            <span className="text-xs text-gray-400 uppercase tracking-wide font-medium">Objekt</span>
            <span className="text-gray-300">|</span>
            {selectedNummer && (
              <span className="text-xs font-mono text-gray-500">{selectedNummer}</span>
            )}
            <Link
              to={`/objekte/${selectedId}`}
              className="text-sm font-semibold text-primary-700 hover:underline"
            >
              {selectedName}
            </Link>
            {selectedTyp && (
              <span className="text-xs bg-primary-50 text-primary-700 border border-primary-200 px-1.5 py-0.5 rounded font-medium">
                {selectedTyp}
              </span>
            )}
            <button
              onClick={clearSelected}
              className="ml-auto text-xs text-gray-400 hover:text-gray-600 transition-colors"
              title="Objektauswahl aufheben"
            >
              ✕ Abwählen
            </button>
          </div>
        )}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
