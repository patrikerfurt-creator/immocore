import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { personenApi } from '../../api/personen'
import { PersonForm } from './PersonForm'
import { Button } from '../../components/ui/Button'

export function PersonDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [editMode, setEditMode] = useState(false)

  const { data: person, isLoading } = useQuery({
    queryKey: ['person', id],
    queryFn: () => personenApi.get(id!),
    enabled: !!id,
  })

  const { data: evs } = useQuery({
    queryKey: ['eigentumsverhaeltnisse', id],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ person: id! }),
    enabled: !!id,
  })

  if (isLoading) return <p className="text-gray-400">Laden…</p>
  if (!person) return <p className="text-gray-400">Person nicht gefunden.</p>

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => navigate('/personen')}
            className="text-sm text-gray-500 hover:text-gray-700 mb-1 flex items-center gap-1"
          >
            ← Zurück
          </button>
          <h1 className="text-2xl font-bold text-gray-900">{person.name}</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {(person as unknown as Record<string, string>).personennummer || ''}
          </p>
        </div>
        <Button
          variant={editMode ? 'secondary' : 'primary'}
          onClick={() => setEditMode(v => !v)}
        >
          {editMode ? 'Abbrechen' : 'Bearbeiten'}
        </Button>
      </div>

      {editMode ? (
        <PersonForm person={person} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Stammdaten */}
          <div className="rounded-lg border border-gray-200 p-5 space-y-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Stammdaten</h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Anrede</dt>
                <dd className="text-gray-800">{(person as unknown as Record<string, string>).anrede || '–'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Typ</dt>
                <dd className="text-gray-800">{person.person_typ}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">E-Mail</dt>
                <dd className="text-gray-800">{person.email || '–'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Telefon</dt>
                <dd className="text-gray-800">{person.telefon || '–'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Adresse</dt>
                <dd className="text-gray-800 text-right whitespace-pre-line">
                  {(person as unknown as Record<string, string>).adresse || '–'}
                </dd>
              </div>
            </dl>
          </div>

          {/* IBANs */}
          <div className="rounded-lg border border-gray-200 p-5 space-y-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">IBANs</h2>
            {person.ibans && person.ibans.length > 0 ? (
              <ul className="space-y-1.5">
                {person.ibans.map((iban, i) => (
                  <li key={i} className="font-mono text-sm text-gray-800 bg-gray-50 rounded px-3 py-1.5">
                    {iban}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400">Keine IBAN hinterlegt.</p>
            )}
          </div>

          {/* Verknüpfte Objekte */}
          <div className="md:col-span-2 rounded-lg border border-gray-200 p-5 space-y-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
              Verknüpfte Einheiten
            </h2>
            {evs && evs.length > 0 ? (
              <table className="w-full text-sm">
                <thead className="border-b border-gray-100">
                  <tr>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Einheit</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Beginn</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Ende</th>
                    <th className="text-left py-2 font-medium text-gray-600">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {evs.map(ev => (
                    <tr key={ev.id} className="border-b border-gray-50">
                      <td className="py-2 pr-4 text-gray-800">{ev.einheit_nr}</td>
                      <td className="py-2 pr-4 text-gray-600">{ev.beginn}</td>
                      <td className="py-2 pr-4 text-gray-600">{ev.ende || '–'}</td>
                      <td className="py-2">
                        {ev.ist_aktiv ? (
                          <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">aktiv</span>
                        ) : (
                          <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">beendet</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-gray-400">Keine Eigentumsverknüpfungen vorhanden.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
