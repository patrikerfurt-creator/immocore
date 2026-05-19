import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi, type Wirtschaftsplan } from '../../api/wirtschaftsplan'
import { objekteApi } from '../../api/objekte'
import { useObjektStore } from '../../stores/objekt'

const STATUS_LABEL: Record<string, string> = {
  entwurf:     'Entwurf',
  beschlossen: 'Beschlossen',
  aktiv:       'Aktiv',
  aufgehoben:  'Aufgehoben',
}
const STATUS_COLOR: Record<string, string> = {
  entwurf:     'bg-gray-100 text-gray-600',
  beschlossen: 'bg-blue-100 text-blue-700',
  aktiv:       'bg-green-100 text-green-700',
  aufgehoben:  'bg-red-100 text-red-500',
}

function fmtDate(iso: string | null) {
  if (!iso) return '–'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

function fmtEur(val: string | null) {
  if (!val) return '–'
  return parseFloat(val).toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €'
}

export function WirtschaftsplanListe() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { selectedId } = useObjektStore()
  const objektId = searchParams.get('objekt') || selectedId || undefined

  const qc = useQueryClient()

  const { data: objekte = [] } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
  })

  const { data: wirtschaftsplaene = [], isLoading } = useQuery({
    queryKey: ['wirtschaftsplaene', objektId],
    queryFn: () => wirtschaftsplanApi.list({ objekt: objektId }),
    enabled: !!objektId,
  })

  const { data: wirtschaftsjahre = [] } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () =>
      fetch(`/api/v1/wirtschaftsjahre/?objekt=${objektId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access')}` },
      }).then(r => r.json()),
    enabled: !!objektId,
  })

  const [showNeu, setShowNeu] = useState(false)
  const [neuWjId, setNeuWjId] = useState('')
  const [neuWirkungAb, setNeuWirkungAb] = useState('')

  const createMut = useMutation({
    mutationFn: () =>
      wirtschaftsplanApi.create({ wirtschaftsjahr: neuWjId, wirkung_ab: neuWirkungAb }),
    onSuccess: (wp: Wirtschaftsplan) => {
      qc.invalidateQueries({ queryKey: ['wirtschaftsplaene'] })
      setShowNeu(false)
      navigate(`/abrechnung-wp/wirtschaftsplan/${wp.id}/wizard`)
    },
  })

  const objekt = objekte.find((o: any) => o.id === objektId)

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Wirtschaftspläne</h1>
          {objekt && <p className="text-sm text-gray-500 mt-1">{objekt.objektnummer} — {objekt.bezeichnung}</p>}
        </div>
        {objektId && (
          <button
            onClick={() => setShowNeu(true)}
            className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700"
          >
            + Neuer Wirtschaftsplan
          </button>
        )}
      </div>

      {!objektId && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700">
          Bitte ein Objekt aus der Objektauswahl wählen.
        </div>
      )}

      {showNeu && (
        <div className="mb-6 rounded-lg border border-gray-200 p-4 bg-white shadow-sm">
          <h2 className="font-semibold text-gray-800 mb-3">Neuen Wirtschaftsplan anlegen</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Wirtschaftsjahr</label>
              <select
                value={neuWjId}
                onChange={e => {
                  setNeuWjId(e.target.value)
                  const wj = wirtschaftsjahre.find((w: any) => w.id === e.target.value)
                  if (wj) setNeuWirkungAb(`${wj.jahr}-${String(wj.beginn_monat).padStart(2,'0')}-01`)
                }}
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
              >
                <option value="">– wählen –</option>
                {wirtschaftsjahre.map((wj: any) => (
                  <option key={wj.id} value={wj.id}>WJ {wj.jahr} [{wj.status}]</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Wirkung ab</label>
              <input
                type="date"
                value={neuWirkungAb}
                onChange={e => setNeuWirkungAb(e.target.value)}
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
              />
            </div>
          </div>
          <div className="flex gap-2 mt-3 justify-end">
            <button onClick={() => setShowNeu(false)} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5">
              Abbrechen
            </button>
            <button
              onClick={() => createMut.mutate()}
              disabled={!neuWjId || !neuWirkungAb || createMut.isPending}
              className="bg-primary-600 text-white px-4 py-1.5 rounded text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
            >
              {createMut.isPending ? 'Anlegen…' : 'Anlegen & Wizard starten'}
            </button>
          </div>
        </div>
      )}

      {isLoading && <p className="text-sm text-gray-400">Laden…</p>}

      {!isLoading && wirtschaftsplaene.length === 0 && objektId && (
        <p className="text-sm text-gray-400">Keine Wirtschaftspläne vorhanden.</p>
      )}

      {wirtschaftsplaene.length > 0 && (
        <div className="rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">WJ</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">Wirkung ab</th>
                <th className="text-right px-4 py-2.5 font-medium text-gray-600">Gesamtsumme</th>
                <th className="text-right px-4 py-2.5 font-medium text-gray-600">Beschluss</th>
                <th className="text-right px-4 py-2.5 font-medium text-gray-600">Positionen</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {wirtschaftsplaene.map((wp: Wirtschaftsplan) => (
                <tr key={wp.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-medium text-gray-800">WJ {wp.wj_jahr}</td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[wp.status]}`}>
                      {STATUS_LABEL[wp.status]}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">{fmtDate(wp.wirkung_ab)}</td>
                  <td className="px-4 py-2.5 text-right text-gray-700">{fmtEur(wp.gesamtsumme)}</td>
                  <td className="px-4 py-2.5 text-right text-gray-500">{fmtDate(wp.beschluss_datum)}</td>
                  <td className="px-4 py-2.5 text-right text-gray-500">{wp.anzahl_positionen ?? '–'}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => navigate(`/abrechnung-wp/wirtschaftsplan/${wp.id}`)}
                      className="text-xs text-primary-600 hover:text-primary-700 underline"
                    >
                      Öffnen
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
