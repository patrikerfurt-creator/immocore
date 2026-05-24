import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../../components/ui/Button'
import { mitarbeiterApi } from '../../../api/mitarbeiter'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

export function Step08_Betreuer({ initialData, onWeiter, isLoading, errors }: StepProps) {
  const [betreuerId, setBetreuerId] = useState<string>(
    (initialData.betreuer as string) ?? ''
  )
  const [vertretungId, setVertretungId] = useState<string>(
    (initialData.betreuer_vertretung as string) ?? ''
  )

  const { data: mitarbeiter } = useQuery({
    queryKey: ['mitarbeiter-aktiv'],
    queryFn: () => mitarbeiterApi.list({ aktiv: 'true' }),
  })

  const aktive = (mitarbeiter ?? []).filter(m => m.aktiv)

  const handleWeiter = async () => {
    if (!betreuerId) return
    await onWeiter({
      betreuer: betreuerId,
      betreuer_vertretung: vertretungId || null,
    })
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-600">
        Der Objektbetreuer ist das direkte Routing-Ziel für erkannte Rechnungen dieses Objekts
        (Erkennungsstufe 2). Bei Abwesenheit übernimmt die Vertretung.
      </p>

      {/* Betreuer (Pflicht) */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Objektbetreuer <span className="text-red-500">*</span>
        </label>
        <select
          value={betreuerId}
          onChange={e => setBetreuerId(e.target.value)}
          className="border rounded px-3 py-2 text-sm w-full max-w-sm"
        >
          <option value="">— Betreuer wählen —</option>
          {aktive.map(m => (
            <option key={m.id} value={m.id}>{m.vollname || `${m.vorname} ${m.nachname}`}</option>
          ))}
        </select>
        <p className="text-xs text-gray-400 mt-1">
          Muss Sachbearbeiter, Geschäftsführer, Administrator oder Frontoffice-Rolle haben.
        </p>
      </div>

      {/* Betreuer-Vertretung (optional) */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Vertretung bei Abwesenheit <span className="text-gray-400 font-normal">(optional)</span>
        </label>
        <select
          value={vertretungId}
          onChange={e => setVertretungId(e.target.value)}
          className="border rounded px-3 py-2 text-sm w-full max-w-sm"
        >
          <option value="">— Keine Vertretung —</option>
          {aktive
            .filter(m => m.id !== betreuerId)
            .map(m => (
              <option key={m.id} value={m.id}>{m.vollname || `${m.vorname} ${m.nachname}`}</option>
            ))}
        </select>
        <p className="text-xs text-gray-400 mt-1">
          Wird automatisch zugewiesen wenn Betreuer als abwesend markiert ist.
        </p>
      </div>

      {errors.length > 0 && (
        <div className="rounded bg-red-50 border border-red-200 p-3 space-y-1">
          {errors.map((e, i) => (
            <p key={i} className="text-sm text-red-700">{e}</p>
          ))}
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <Button onClick={handleWeiter} disabled={!betreuerId || isLoading}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </div>
  )
}
