import React, { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
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

interface HausgeldEintrag {
  abrechnungsart_code: string
  betrag: string
}

interface VertragRow {
  einheit_nr: string
  person_id: string
  person_name: string
  beginn: string
  hausgeld_eintraege: HausgeldEintrag[]
}

interface AbrechnungsartDef {
  code: string
  bezeichnung: string
}

function getEinheiten(stepsData: Record<string, unknown>): { einheit_nr: string }[] {
  const s5 = (stepsData['5'] ?? {}) as Record<string, unknown>
  if (Array.isArray(s5.einheiten)) {
    return (s5.einheiten as Record<string, string>[]).map(e => ({
      einheit_nr: e.wohnungsbezeichnung ?? e.einheit_nr ?? '',
    }))
  }
  return []
}

function getAbrechnungsarten(stepsData: Record<string, unknown>): AbrechnungsartDef[] {
  const abr: AbrechnungsartDef[] = [{ code: '900', bezeichnung: 'Hausgeld' }]
  const s6 = (stepsData['6'] ?? {}) as Record<string, unknown>
  if (Array.isArray(s6.ruecklagenkonten)) {
    ;(s6.ruecklagenkonten as { bezeichnung?: string; reihenfolge?: number }[]).forEach((r, i) => {
      const reihenfolge = r.reihenfolge ?? i + 1
      const code = String(910 + reihenfolge)
      abr.push({ code, bezeichnung: r.bezeichnung || `Rücklage ${reihenfolge}` })
    })
  } else {
    abr.push({ code: '911', bezeichnung: 'Instandhaltungsrücklage' })
  }
  return abr
}

function buildInitialRows(
  einheiten: { einheit_nr: string }[],
  abrArten: AbrechnungsartDef[],
  initialData: Record<string, unknown>
): VertragRow[] {
  if (Array.isArray(initialData.vertraege) && (initialData.vertraege as VertragRow[]).length > 0) {
    return (initialData.vertraege as Partial<VertragRow>[]).map(v => ({
      einheit_nr: v.einheit_nr ?? '',
      person_id: v.person_id ?? '',
      person_name: v.person_name ?? '',
      beginn: v.beginn ?? '',
      hausgeld_eintraege: v.hausgeld_eintraege ?? abrArten.map(a => ({ abrechnungsart_code: a.code, betrag: '' })),
    }))
  }
  return einheiten.map(e => ({
    einheit_nr: e.einheit_nr,
    person_id: '',
    person_name: '',
    beginn: '',
    hausgeld_eintraege: abrArten.map(a => ({ abrechnungsart_code: a.code, betrag: '' })),
  }))
}

/**
 * Durchsuchbare Eigentümer-Auswahl (Server-Suche ab 2 Zeichen).
 * Die Trefferliste wird per Portal mit fester Position gerendert, damit sie
 * nicht vom horizontal scrollenden Tabellen-Container abgeschnitten wird.
 */
function PersonCombobox({
  personId, personName, onSelect,
}: {
  personId: string
  personName: string
  onSelect: (p: PersonList | null) => void
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const { data: results, isFetching } = useQuery({
    queryKey: ['personen-search', query],
    queryFn: () => personenApi.list({ search: query }),
    enabled: open && query.length >= 2,
    staleTime: 10_000,
  })

  const updateRect = () => {
    if (inputRef.current) setRect(inputRef.current.getBoundingClientRect())
  }

  const openDropdown = () => { updateRect(); setOpen(true) }
  const closeDropdown = () => { setOpen(false); setQuery('') }

  // Position bei Scroll/Resize nachführen und Klick-außerhalb erkennen
  useEffect(() => {
    if (!open) return
    const onScrollOrResize = () => updateRect()
    const onMouseDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (inputRef.current?.contains(t)) return
      if (dropdownRef.current?.contains(t)) return
      closeDropdown()
    }
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
    document.addEventListener('mousedown', onMouseDown)
    return () => {
      window.removeEventListener('scroll', onScrollOrResize, true)
      window.removeEventListener('resize', onScrollOrResize)
      document.removeEventListener('mousedown', onMouseDown)
    }
  }, [open])

  // Bereits gewählter Eigentümer → als Chip anzeigen
  if (personId) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary-50 text-primary-700 text-sm font-medium max-w-full">
        <span className="truncate">{personName || 'Eigentümer gewählt'}</span>
        <button
          type="button"
          onClick={() => onSelect(null)}
          className="text-primary-400 hover:text-primary-700 leading-none"
          aria-label="Eigentümer entfernen"
        >
          ×
        </button>
      </span>
    )
  }

  return (
    <>
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={e => { setQuery(e.target.value); if (!open) setOpen(true); updateRect() }}
        onFocus={openDropdown}
        placeholder="Name oder E-Mail suchen…"
        className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
      />
      {open && rect && createPortal(
        <div
          ref={dropdownRef}
          style={{ position: 'fixed', top: rect.bottom + 4, left: rect.left, width: Math.max(rect.width, 260) }}
          className="z-50 bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-y-auto"
        >
          {query.length < 2 ? (
            <div className="px-3 py-4 text-sm text-gray-400 text-center">Mindestens 2 Zeichen eingeben…</div>
          ) : isFetching ? (
            <div className="px-3 py-4 text-sm text-gray-400 text-center">Suche…</div>
          ) : results && results.length > 0 ? (
            results.map(p => (
              <button
                key={p.id}
                type="button"
                onClick={() => { onSelect(p); closeDropdown() }}
                className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b border-gray-100 last:border-0"
              >
                <div className="text-sm font-medium text-gray-800">{p.name}</div>
                <div className="text-xs text-gray-400">{p.email || '–'}</div>
              </button>
            ))
          ) : (
            <div className="px-3 py-4 text-sm text-gray-400 text-center">Keine Person gefunden.</div>
          )}
        </div>,
        document.body
      )}
    </>
  )
}

export function Step08_Vertraege({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const einheiten = getEinheiten(stepsData)
  const abrArten = getAbrechnungsarten(stepsData)

  const [rows, setRows] = useState<VertragRow[]>(() =>
    buildInitialRows(einheiten, abrArten, initialData)
  )

  const setPerson = (einheitNr: string, p: PersonList | null) => {
    setRows(prev => prev.map(r =>
      r.einheit_nr === einheitNr
        ? { ...r, person_id: p?.id ?? '', person_name: p?.name ?? '' }
        : r
    ))
  }

  const updateBeginn = (einheitNr: string, value: string) => {
    setRows(prev => prev.map(r =>
      r.einheit_nr === einheitNr ? { ...r, beginn: value } : r
    ))
  }

  const updateBetrag = (einheitNr: string, code: string, value: string) => {
    setRows(prev => prev.map(r => {
      if (r.einheit_nr !== einheitNr) return r
      return {
        ...r,
        hausgeld_eintraege: r.hausgeld_eintraege.map(h =>
          h.abrechnungsart_code === code ? { ...h, betrag: value } : h
        ),
      }
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const vertraege = rows
      .filter(r => r.person_id && r.beginn)
      .map(r => ({
        einheit_nr: r.einheit_nr,
        person_id: r.person_id,
        person_name: r.person_name,
        beginn: r.beginn,
        hausgeld_eintraege: r.hausgeld_eintraege.filter(h => h.betrag !== ''),
      }))
    await onWeiter({ vertraege })
  }

  const besetztCount = rows.filter(r => r.person_id && r.beginn).length

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-gray-600">
        Legen Sie Vertragsbeginn und monatliche Sollbeträge für jede Einheit fest.
        Einheiten ohne Eigentümer können übersprungen und später per CSV-Import ergänzt werden.
      </p>

      {einheiten.length === 0 && (
        <div className="rounded-md bg-amber-50 p-3">
          <p className="text-sm text-amber-700">Keine Einheiten gefunden. Bitte Schritt 5 (Einheiten) zuerst ausfüllen.</p>
        </div>
      )}

      {einheiten.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm" style={{ minWidth: `${560 + abrArten.length * 110}px` }}>
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Einheit</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Eigentümer</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Beginn</th>
                {abrArten.map(a => (
                  <th key={a.code} className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">
                    .{a.code}
                    <span className="block text-xs font-normal text-gray-400">{a.bezeichnung}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.einheit_nr} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-700 whitespace-nowrap">{row.einheit_nr}</td>
                  <td className="px-3 py-2 min-w-[200px]">
                    <PersonCombobox
                      personId={row.person_id}
                      personName={row.person_name}
                      onSelect={p => setPerson(row.einheit_nr, p)}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="date"
                      value={row.beginn}
                      onChange={e => updateBeginn(row.einheit_nr, e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[130px]"
                    />
                  </td>
                  {abrArten.map(a => {
                    const h = row.hausgeld_eintraege.find(x => x.abrechnungsart_code === a.code)
                    return (
                      <td key={a.code} className="px-3 py-2">
                        <input
                          type="number"
                          value={h?.betrag ?? ''}
                          onChange={e => updateBetrag(row.einheit_nr, a.code, e.target.value)}
                          className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[90px]"
                          placeholder="0.00"
                          min={0}
                          step="0.01"
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {besetztCount < rows.length && rows.length > 0 && (
        <p className="text-xs text-amber-600">
          {rows.length - besetztCount} Einheit(en) ohne Eigentümer werden übersprungen.
        </p>
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
