import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../../components/ui/Button'
import { objekteApi } from '../../../api/objekte'
import { personenApi } from '../../../api/personen'
import type { Einheit, EigentumsVerhaeltnis } from '../../../types'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

function fmtDate(iso: string): string {
  if (!iso) return '–'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

function monatsersterNach(stichtag: string): string {
  if (!stichtag) return ''
  const d = new Date(stichtag)
  if (d.getDate() === 1) return stichtag
  const next = new Date(d.getFullYear(), d.getMonth() + 1, 1)
  return next.toISOString().slice(0, 10)
}

function isRueckwirkend(wp: string): boolean {
  if (!wp) return false
  const heute = new Date()
  const erster = new Date(heute.getFullYear(), heute.getMonth(), 1)
  return new Date(wp) < erster
}

export function EW_Step01_EinheitStichtag({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const objektId = (stepsData as { objekt_id?: string }).objekt_id as string | undefined

  const [einheitId, setEinheitId] = useState<string>((initialData.einheit_id as string) ?? '')
  const [stichtag, setStichtag] = useState<string>((initialData.stichtag as string) ?? '')
  const [wechselGrund, setWechselGrund] = useState<string>((initialData.wechsel_grund as string) ?? 'verkauf')

  const { data: einheiten } = useQuery({
    queryKey: ['einheiten', objektId],
    queryFn: () => objekteApi.listEinheiten({ objekt: objektId! }),
    enabled: !!objektId,
  })

  const { data: evListe } = useQuery({
    queryKey: ['ev-einheit', einheitId],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ einheit: einheitId }),
    enabled: !!einheitId,
  })
  const aktivesEv = evListe?.find((ev: EigentumsVerhaeltnis) => ev.ist_aktiv)

  const wirkungs_periode = monatsersterNach(stichtag)
  const art = isRueckwirkend(wirkungs_periode) ? 'rueckwirkend' : 'zukuenftig'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!einheitId) { return }
    if (!stichtag) { return }
    await onWeiter({ einheit_id: einheitId, stichtag, wechsel_grund: wechselGrund, wirkungs_periode, art })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Einheit *</label>
        <select
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
          value={einheitId}
          onChange={e => setEinheitId(e.target.value)}
          required
        >
          <option value="">Einheit wählen…</option>
          {einheiten?.map((e: Einheit) => (
            <option key={e.id} value={e.id}>
              {e.einheit_nr} — {e.lage}
            </option>
          ))}
        </select>
      </div>

      {einheitId && (
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-sm">
          {aktivesEv ? (
            <span>
              <span className="font-medium">Aktueller Eigentümer:</span>{' '}
              {aktivesEv.person_name}{' '}
              <span className="text-gray-400">(seit {fmtDate(aktivesEv.beginn)})</span>
            </span>
          ) : (
            <span className="text-amber-600">Kein aktiver Eigentümer gefunden — Wechsel nicht möglich.</span>
          )}
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Stichtag (Eigentumsumschreibung lt. Notar) *</label>
        <input
          type="date"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={stichtag}
          onChange={e => setStichtag(e.target.value)}
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Wechsel-Grund</label>
        <select
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
          value={wechselGrund}
          onChange={e => setWechselGrund(e.target.value)}
        >
          <option value="verkauf">Verkauf</option>
          <option value="erbfolge">Erbfolge</option>
          <option value="zwangsversteigerung">Zwangsversteigerung</option>
          <option value="sonstiges">Sonstiges</option>
        </select>
      </div>

      {stichtag && (
        <div className={`rounded-md p-3 text-sm ${art === 'rueckwirkend' ? 'bg-amber-50 border border-amber-200' : 'bg-blue-50 border border-blue-200'}`}>
          <p><span className="font-medium">Wirkungsperiode:</span> {fmtDate(wirkungs_periode)}</p>
          <p><span className="font-medium">Art:</span> {art === 'rueckwirkend' ? '⚠ Rückwirkend' : 'Zukünftig'}</p>
          {art === 'rueckwirkend' && (
            <p className="mt-1 text-amber-700">Stichtag liegt in der Vergangenheit. Schritt 4 zeigt die zu korrigierenden Sollstellungen.</p>
          )}
        </div>
      )}

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading || !einheitId || !stichtag || !aktivesEv}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
