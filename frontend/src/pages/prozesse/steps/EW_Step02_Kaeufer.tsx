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

function PersonSearch({
  value, name, onSelect,
}: {
  value: string
  name: string
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

  if (value) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary-50 text-primary-700 text-sm font-medium">
        {name}
        <button type="button" onClick={() => onSelect(null)} className="text-primary-400 hover:text-primary-700 leading-none">×</button>
      </span>
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
              <button key={p.id} type="button"
                onClick={() => { onSelect(p); setQuery(''); setOpen(false) }}
                className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b border-gray-100 last:border-0"
              >
                <div className="text-sm font-medium text-gray-800">{p.name}</div>
                <div className="text-xs text-gray-400">{p.email || '–'}</div>
              </button>
            ))
          ) : (
            <div className="px-3 py-4 text-sm text-gray-400 text-center">Keine Person gefunden.</div>
          )}
        </div>
      )}
    </div>
  )
}

const IBAN_RE = /^DE\d{20}$/

export function EW_Step02_Kaeufer({ initialData, onWeiter, isLoading, errors }: StepProps) {
  const [kaeuferPersonId, setKaeuferPersonId] = useState<string>((initialData.kaeufer_person_id as string) ?? '')
  const [kaeuferPersonName, setKaeuferPersonName] = useState<string>((initialData.kaeufer_person_name as string) ?? '')
  const [kaeuferIban, setKaeuferIban] = useState<string>((initialData.kaeufer_iban as string) ?? '')

  const ibanValid = !kaeuferIban || IBAN_RE.test(kaeuferIban.replace(/\s/g, '').toUpperCase())

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!kaeuferPersonId) return
    const iban = kaeuferIban.replace(/\s/g, '').toUpperCase()
    await onWeiter({ kaeufer_person_id: kaeuferPersonId, kaeufer_person_name: kaeuferPersonName, kaeufer_iban: iban })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="flex items-start justify-between">
        <p className="text-sm text-gray-500">Person aus dem Stammdaten-Register wählen oder neu anlegen.</p>
        <Link to="/personen/neu" target="_blank" className="text-sm text-primary-600 hover:text-primary-700 font-medium whitespace-nowrap ml-4">
          + Neue Person anlegen
        </Link>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Käufer (Person) *</label>
        <PersonSearch
          value={kaeuferPersonId}
          name={kaeuferPersonName}
          onSelect={p => {
            setKaeuferPersonId(p?.id ?? '')
            setKaeuferPersonName(p?.name ?? '')
          }}
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">IBAN für Lastschrift</label>
        <input
          type="text"
          className={`w-full rounded border px-3 py-2 text-sm ${!ibanValid ? 'border-red-400' : 'border-gray-300'}`}
          value={kaeuferIban}
          onChange={e => setKaeuferIban(e.target.value)}
          placeholder="DE89…"
          maxLength={34}
        />
        {!ibanValid && <p className="text-xs text-red-600 mt-1">IBAN muss im Format DE + 20 Ziffern sein.</p>}
      </div>

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading || !kaeuferPersonId}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
