import { useState } from 'react'
import { type Wirtschaftsplan } from '../../../api/wirtschaftsplan'

interface Props {
  wp: Wirtschaftsplan
  isLoading: boolean
  errors: string[]
  onSaveEntwurf: () => void
  onBeschluss: (data: { beschluss_datum: string; top?: string; bemerkung?: string }) => void
  onZurueck: () => void
}

function fmtEur(val: string | null) {
  if (!val) return '–'
  return parseFloat(val).toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €'
}

export function Schritt5_Beschluss({ wp, isLoading, errors, onSaveEntwurf, onBeschluss, onZurueck }: Props) {
  const [beschlussDatum, setBeschlussDatum] = useState(
    new Date().toISOString().split('T')[0]
  )
  const [top, setTop] = useState('')
  const [bemerkung, setBemerkung] = useState(wp.bemerkung ?? '')

  const isRueckwirkend = beschlussDatum < wp.wirkung_ab

  const handleBeschluss = () => {
    onBeschluss({
      beschluss_datum: beschlussDatum,
      top: top.trim() || undefined,
      bemerkung: bemerkung.trim() || undefined,
    })
  }

  const positionen = wp.positionen ?? []
  const hausgeldMonatl = parseFloat(wp.gesamtsumme_hausgeld) / 12

  return (
    <div>
      <h2 className="text-base font-semibold text-gray-800 mb-1">Beschluss erfassen</h2>
      <p className="text-sm text-gray-500 mb-6">
        Beschlussdatum und Tagesordnungspunkt eintragen, dann den Wirtschaftsplan beschließen.
      </p>

      {/* Zusammenfassung */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4 text-center">
          <p className="text-xs text-gray-500 mb-1">Positionen</p>
          <p className="text-2xl font-bold text-gray-800">{positionen.length}</p>
        </div>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4 text-center">
          <p className="text-xs text-gray-500 mb-1">Jahressumme</p>
          <p className="text-xl font-bold text-gray-800">{fmtEur(wp.gesamtsumme)}</p>
        </div>
        <div className="rounded-lg bg-primary-50 border border-primary-200 p-4 text-center">
          <p className="text-xs text-primary-600 mb-1">Hausgeld mtl. gesamt</p>
          <p className="text-xl font-bold text-primary-700">
            {isNaN(hausgeldMonatl) ? '–' : hausgeldMonatl.toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €'}
          </p>
        </div>
      </div>

      {/* Wirkung-ab Info */}
      <div className="rounded-md bg-blue-50 border border-blue-200 p-3 mb-5 text-sm text-blue-700">
        Wirkung ab: <strong>{wp.wirkung_ab}</strong>
        {isRueckwirkend && (
          <span className="ml-2 text-amber-700 font-medium">
            ⚠ Rückwirkend — Nachhol-Sollstellungen und ggf. Gutschriften werden automatisch erzeugt.
          </span>
        )}
      </div>

      {/* Formular */}
      <div className="space-y-4 mb-6">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Beschlussdatum <span className="text-red-500">*</span>
          </label>
          <input
            type="date"
            value={beschlussDatum}
            onChange={e => setBeschlussDatum(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 text-sm w-48 focus:outline-none focus:border-primary-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Tagesordnungspunkt (TOP)
          </label>
          <input
            type="text"
            value={top}
            onChange={e => setTop(e.target.value)}
            placeholder="z.B. TOP 3"
            className="border border-gray-300 rounded px-3 py-2 text-sm w-64 focus:outline-none focus:border-primary-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Bemerkung</label>
          <textarea
            value={bemerkung}
            onChange={e => setBemerkung(e.target.value)}
            rows={3}
            className="border border-gray-300 rounded px-3 py-2 text-sm w-full focus:outline-none focus:border-primary-500"
            placeholder="Optionale Anmerkungen zum Beschluss…"
          />
        </div>
      </div>

      {errors.length > 0 && (
        <div className="mb-4 rounded-md bg-red-50 border border-red-200 p-3">
          {errors.map((e, i) => <p key={i} className="text-sm text-red-600">{e}</p>)}
        </div>
      )}

      <div className="flex justify-between items-center">
        <button onClick={onZurueck} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2">
          ← Zurück
        </button>
        <div className="flex gap-3">
          <button
            onClick={onSaveEntwurf}
            className="border border-gray-300 text-gray-600 px-4 py-2 rounded text-sm font-medium hover:bg-gray-50"
          >
            Als Entwurf speichern
          </button>
          <button
            onClick={handleBeschluss}
            disabled={!beschlussDatum || isLoading}
            className="bg-primary-600 text-white px-6 py-2 rounded text-sm font-medium hover:bg-primary-700 disabled:opacity-40"
          >
            {isLoading ? 'Wird beschlossen…' : '✓ Wirtschaftsplan beschließen'}
          </button>
        </div>
      </div>
    </div>
  )
}
