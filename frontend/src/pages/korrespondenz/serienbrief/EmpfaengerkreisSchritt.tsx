import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { personenApi } from '../../../api/personen'
import type { ObjektList } from '../../../types'
import { EINHEIT_TYPEN, type Ausnahme, type EmpfaengerAuswahl } from './empfaengerFilter'

interface Props {
  objekte: ObjektList[]
  objektId: string
  /** Gesetzt, wenn die Vorlage zu genau einem Objekt gehört — dann ist das Objekt nicht wählbar. */
  objektFest: boolean
  onObjekt: (id: string) => void
  auswahl: EmpfaengerAuswahl
  onChange: (auswahl: EmpfaengerAuswahl) => void
}

const feld = 'mt-1 w-full border border-gray-300 rounded px-2 py-1.5 text-sm'

/** Schritt 2 des Serienbrief-Assistenten: Objekt, Filter und manuelle Ab-/Zuwahl (Spec 7.4). */
export function EmpfaengerkreisSchritt({ objekte, objektId, objektFest, onObjekt, auswahl, onChange }: Props) {
  const [suche, setSuche] = useState('')

  const { data: evs, isLoading } = useQuery({
    queryKey: ['korrespondenz-serienbrief-ev', objektId],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ objekt: objektId }),
    enabled: !!objektId,
  })

  const sichtbar = useMemo(() => {
    const s = suche.trim().toLowerCase()
    return (evs ?? []).filter(ev => !s
      || ev.person_name.toLowerCase().includes(s) || ev.einheit_nr.toLowerCase().includes(s))
  }, [evs, suche])

  const typUmschalten = (typ: string) => onChange({
    ...auswahl,
    einheit_typ: auswahl.einheit_typ.includes(typ)
      ? auswahl.einheit_typ.filter(t => t !== typ)
      : [...auswahl.einheit_typ, typ],
  })

  const ausnahmeSetzen = (evId: string, wert: '' | Ausnahme) => {
    const ausnahmen = { ...auswahl.ausnahmen }
    if (wert) ausnahmen[evId] = wert
    else delete ausnahmen[evId]
    onChange({ ...auswahl, ausnahmen })
  }

  return (
    <div className="space-y-4">
      <label className="block text-sm max-w-md">
        <span className="text-gray-700">Objekt *</span>
        <select value={objektId} disabled={objektFest} onChange={e => onObjekt(e.target.value)} className={feld}>
          <option value="">— wählen —</option>
          {objekte.map(o => <option key={o.id} value={o.id}>{o.objektnummer} {o.bezeichnung}</option>)}
        </select>
        {objektFest && <span className="text-xs text-gray-500">Die gewählte Vorlage gehört zu diesem Objekt.</span>}
      </label>

      <p className="text-sm text-gray-600">
        Empfänger sind die aktiven Eigentümer des Objekts — je Eigentumsverhältnis ein Schreiben.
      </p>

      <fieldset className="border border-gray-200 rounded p-3 space-y-2">
        <legend className="text-xs text-gray-500 px-1">Einheitstyp (keine Auswahl = alle)</legend>
        <div className="flex flex-wrap gap-4">
          {EINHEIT_TYPEN.map(typ => (
            <label key={typ} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={auswahl.einheit_typ.includes(typ)} onChange={() => typUmschalten(typ)} />
              {typ}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="border border-gray-200 rounded p-3 space-y-2">
        <legend className="text-xs text-gray-500 px-1">E-Mail-Zustimmung</legend>
        <div className="flex flex-wrap gap-4">
          {([['', 'Alle'], ['mit', 'Nur mit Zustimmung'], ['ohne', 'Nur ohne Zustimmung']] as const).map(([wert, label]) => (
            <label key={wert} className="flex items-center gap-1.5 text-sm">
              <input type="radio" name="email_zustimmung" checked={auswahl.email_zustimmung === wert}
                onChange={() => onChange({ ...auswahl, email_zustimmung: wert })} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      {objektId && (
        <fieldset className="border border-gray-200 rounded p-3 space-y-2">
          <legend className="text-xs text-gray-500 px-1">Manuelle Ab- und Zuwahl</legend>
          <input type="search" value={suche} onChange={e => setSuche(e.target.value)}
            placeholder="Eigentümer oder Einheit suchen…" aria-label="Eigentümer oder Einheit suchen"
            className="w-full max-w-sm border border-gray-300 rounded px-2 py-1.5 text-sm" />
          {isLoading && <p className="text-sm text-gray-400">Lade Eigentümer…</p>}
          {evs && (
            <div className="max-h-72 overflow-auto border border-gray-100 rounded">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-600 sticky top-0">
                  <tr>
                    <th className="px-3 py-1.5">Einheit</th>
                    <th className="px-3 py-1.5">Eigentümer</th>
                    <th className="px-3 py-1.5">Zeitraum</th>
                    <th className="px-3 py-1.5">Ausnahme</th>
                  </tr>
                </thead>
                <tbody>
                  {sichtbar.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-3 text-center text-gray-400">Keine Eigentümer gefunden.</td></tr>
                  )}
                  {sichtbar.map(ev => (
                    <tr key={ev.id} className={`border-t border-gray-100 ${ev.ist_aktiv ? '' : 'text-gray-400'}`}>
                      <td className="px-3 py-1.5">{ev.einheit_nr}</td>
                      <td className="px-3 py-1.5">{ev.person_name}</td>
                      <td className="px-3 py-1.5">
                        {ev.beginn} – {ev.ende ?? 'heute'}{ev.ist_aktiv ? '' : ' (beendet)'}
                      </td>
                      <td className="px-3 py-1.5">
                        <select aria-label={`Ausnahme ${ev.person_name} Einheit ${ev.einheit_nr}`}
                          value={auswahl.ausnahmen[ev.id] ?? ''}
                          onChange={e => ausnahmeSetzen(ev.id, e.target.value as '' | Ausnahme)}
                          className="border border-gray-300 rounded px-1.5 py-1 text-sm text-gray-800">
                          <option value="">{ev.ist_aktiv ? 'Standard (laut Filter)' : 'Standard (nicht enthalten)'}</option>
                          {ev.ist_aktiv && <option value="aus">Abwählen</option>}
                          <option value="zu">{ev.ist_aktiv ? 'Immer aufnehmen' : 'Zusätzlich aufnehmen'}</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-gray-500">
            Die genaue Empfängerzahl und eventuelle Probleme zeigt die Vorschau im nächsten Schritt.
          </p>
        </fieldset>
      )}
    </div>
  )
}
