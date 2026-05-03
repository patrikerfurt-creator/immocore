import React, { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../../components/ui/Button'
import { personenApi } from '../../../api/personen'
import type { PersonList } from '../../../types'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

interface Zuordnung {
  wohnungsbezeichnung: string
  person_id: string
  person_name: string
}

function getEinheiten(stepsData: Record<string, unknown>): { wohnungsbezeichnung: string }[] {
  const s4 = (stepsData['4'] ?? {}) as Record<string, unknown>
  if (Array.isArray(s4.einheiten)) {
    return (s4.einheiten as Record<string, string>[]).map(e => ({
      wohnungsbezeichnung: e.wohnungsbezeichnung ?? '',
    }))
  }
  return []
}

function buildInitialZuordnungen(
  einheiten: { wohnungsbezeichnung: string }[],
  initialData: Record<string, unknown>
): Zuordnung[] {
  if (Array.isArray(initialData.zuordnungen) && initialData.zuordnungen.length > 0) {
    return initialData.zuordnungen as Zuordnung[]
  }
  return einheiten.map(e => ({ wohnungsbezeichnung: e.wohnungsbezeichnung, person_id: '', person_name: '' }))
}

function PersonSearch({
  value, onSelect,
}: {
  value: Zuordnung
  onSelect: (p: PersonList | null) => void
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data: results } = useQuery({
    queryKey: ['personen-search', query],
    queryFn: () => personenApi.list({ search: query }),
    enabled: query.length >= 2,
    staleTime: 10_000,
  })

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (value.person_id) {
    return (
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary-50 text-primary-700 text-sm font-medium">
          {value.person_name}
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="text-primary-400 hover:text-primary-700 leading-none"
          >
            ×
          </button>
        </span>
      </div>
    )
  }

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={query}
        onChange={e => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder="Name oder E-Mail suchen…"
        className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
      />
      {open && query.length >= 2 && (
        <div className="absolute z-10 top-full left-0 mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
          {results && results.length > 0 ? (
            results.map(p => (
              <button
                key={p.id}
                type="button"
                onClick={() => { onSelect(p); setQuery(''); setOpen(false) }}
                className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b border-gray-100 last:border-0"
              >
                <div className="text-sm font-medium text-gray-800">{p.name}</div>
                <div className="text-xs text-gray-400">{p.email || '–'}</div>
              </button>
            ))
          ) : (
            <div className="px-3 py-4 text-sm text-gray-400 text-center">
              Keine Person gefunden.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function Step05_Eigentuemer({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const einheiten = getEinheiten(stepsData)
  const [zuordnungen, setZuordnungen] = useState<Zuordnung[]>(() =>
    buildInitialZuordnungen(einheiten, initialData)
  )

  const setZuordnung = (wbez: string, p: PersonList | null) => {
    setZuordnungen(prev => prev.map(z =>
      z.wohnungsbezeichnung === wbez
        ? { ...z, person_id: p?.id ?? '', person_name: p?.name ?? '' }
        : z
    ))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({ zuordnungen })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex items-start justify-between">
        <p className="text-sm text-gray-500">
          Weisen Sie jeder Einheit einen Eigentümer aus dem Personenstamm zu.
        </p>
        <Link
          to="/personen/neu"
          target="_blank"
          className="text-sm text-primary-600 hover:text-primary-700 font-medium whitespace-nowrap ml-4"
        >
          + Neue Person anlegen
        </Link>
      </div>

      {einheiten.length === 0 && (
        <div className="rounded-md bg-amber-50 p-3">
          <p className="text-sm text-amber-700">Keine Einheiten aus Schritt 4 gefunden. Bitte Schritt 4 zuerst ausfüllen.</p>
        </div>
      )}

      {zuordnungen.length > 0 && (
        <div className="rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-40">Einheit</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">Eigentümer *</th>
              </tr>
            </thead>
            <tbody>
              {zuordnungen.map(z => (
                <tr key={z.wohnungsbezeichnung} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-gray-700 whitespace-nowrap">
                    {z.wohnungsbezeichnung}
                  </td>
                  <td className="px-4 py-3">
                    <PersonSearch
                      value={z}
                      onSelect={p => setZuordnung(z.wohnungsbezeichnung, p)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-sm text-red-600">{err}</p>
          ))}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
