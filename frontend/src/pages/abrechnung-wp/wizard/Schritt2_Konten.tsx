import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi, type Wirtschaftsplan, type VerfuegbaresKonto } from '../../../api/wirtschaftsplan'

interface Props {
  wp: Wirtschaftsplan
  onWeiter: () => void
  onZurueck: () => void
}

function fmtEur(val: string | null | undefined) {
  if (!val) return ''
  const n = parseFloat(val)
  return isNaN(n) ? '' : n.toLocaleString('de-DE', { minimumFractionDigits: 2 })
}

export function Schritt2_Konten({ wp, onWeiter, onZurueck }: Props) {
  const qc = useQueryClient()
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [localBetraege, setLocalBetraege] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  const { data: konten = [], isLoading } = useQuery({
    queryKey: ['wp-verfuegbare-konten', wp.id],
    queryFn: () => wirtschaftsplanApi.verfuegbareKonten(wp.id),
  })

  const upsertMut = useMutation({
    mutationFn: ({ konto, betrag }: { konto: string; betrag: string }) =>
      wirtschaftsplanApi.upsertPosition(wp.id, konto, betrag),
    onSuccess: (_, { konto }) => {
      setSaving(s => ({ ...s, [konto]: false }))
      qc.invalidateQueries({ queryKey: ['wirtschaftsplan', wp.id] })
    },
    onError: (err: any, vars) => {
      setSaving(s => ({ ...s, [vars.konto]: false }))
      const msg = err.response?.data?.detail ?? err.response?.data?.betrag?.[0] ?? 'Fehler beim Speichern'
      setErrors(e => ({ ...e, [vars.konto]: msg }))
    },
  })

  const deleteMut = useMutation({
    mutationFn: ({ posId }: { posId: string; konto: string }) =>
      wirtschaftsplanApi.deletePosition(wp.id, posId),
    onSuccess: (_, { konto }) => {
      setSaving(s => ({ ...s, [konto]: false }))
      setLocalBetraege(b => { const n = { ...b }; delete n[konto]; return n })
      qc.invalidateQueries({ queryKey: ['wirtschaftsplan', wp.id] })
    },
    onError: (_, { konto }) => {
      setSaving(s => ({ ...s, [konto]: false }))
    },
  })

  const getAktuellerBetrag = useCallback((k: VerfuegbaresKonto): string => {
    if (localBetraege[k.id] !== undefined) return localBetraege[k.id]
    const pos = wp.positionen?.find(p => p.konto === k.id)
    return pos ? fmtEur(pos.betrag) : ''
  }, [localBetraege, wp.positionen])

  const handleBlur = (k: VerfuegbaresKonto) => {
    const raw = localBetraege[k.id]
    if (raw === undefined) return
    const cleaned = raw.replace(',', '.').trim()
    const num = parseFloat(cleaned)
    if (cleaned === '' || isNaN(num) || num < 0) {
      const pos = wp.positionen?.find(p => p.konto === k.id)
      if (pos && (cleaned === '' || isNaN(num))) {
        setSaving(s => ({ ...s, [k.id]: true }))
        deleteMut.mutate({ posId: pos.id, konto: k.id })
      }
      return
    }
    setErrors(e => { const n = { ...e }; delete n[k.id]; return n })
    setSaving(s => ({ ...s, [k.id]: true }))
    upsertMut.mutate({ konto: k.id, betrag: num.toFixed(2) })
  }

  const posMap = Object.fromEntries((wp.positionen ?? []).map(p => [p.konto, p]))
  const gesamtSumme = (wp.positionen ?? []).reduce((s, p) => s + parseFloat(p.betrag), 0)
  const hausgeldSumme = (wp.positionen ?? [])
    .filter(p => {
      const k = konten.find((kk: VerfuegbaresKonto) => kk.id === p.konto)
      return k?.abrechnungsart != null
    })
    .reduce((s, p) => s + parseFloat(p.betrag), 0)

  return (
    <div>
      <h2 className="text-base font-semibold text-gray-800 mb-1">Konten & Beträge</h2>
      <p className="text-sm text-gray-500 mb-4">
        Jahresbeträge eingeben. Nur Konten 50000–55999 und 57xxx sind wählbar.
      </p>

      {isLoading ? (
        <p className="text-sm text-gray-400">Lade Konten…</p>
      ) : (
        <div className="rounded-lg border border-gray-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-20">Konto</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">Bezeichnung</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-16">VS</th>
                <th className="text-right px-4 py-2.5 font-medium text-gray-600 w-40">Jahresbetrag (€)</th>
                <th className="text-right px-4 py-2.5 font-medium text-gray-600 w-32">Monatlich</th>
              </tr>
            </thead>
            <tbody>
              {konten.map(k => {
                const betragStr = getAktuellerBetrag(k)
                const betragNum = parseFloat(betragStr.replace(',', '.')) || 0
                const monatlich = betragNum / 12
                const isSaving = saving[k.id]
                const err = errors[k.id]
                const pos = posMap[k.id]

                return (
                  <tr key={k.id} className={`border-t border-gray-100 ${pos ? 'bg-white' : 'bg-gray-50/50'}`}>
                    <td className="px-4 py-2 font-mono text-gray-500 text-xs">{k.kontonummer}</td>
                    <td className="px-4 py-2 text-gray-700">
                      {k.kontoname}
                      <span className="ml-2 text-xs text-gray-400">{k.kontoart}</span>
                      {err && <p className="text-xs text-red-500 mt-0.5">{err}</p>}
                    </td>
                    <td className="px-4 py-2 text-gray-400 font-mono text-xs">{k.vs_code ?? '–'}</td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1 justify-end">
                        {isSaving && <span className="text-xs text-gray-400">…</span>}
                        <input
                          type="text"
                          inputMode="decimal"
                          value={betragStr}
                          onChange={e => {
                            setLocalBetraege(b => ({ ...b, [k.id]: e.target.value }))
                            setErrors(err => { const n = { ...err }; delete n[k.id]; return n })
                          }}
                          onBlur={() => handleBlur(k)}
                          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
                          placeholder="0,00"
                          className={`w-28 text-right border rounded px-2 py-1 text-sm ${
                            err ? 'border-red-400' : 'border-gray-300'
                          } focus:outline-none focus:border-primary-500`}
                        />
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right text-gray-500 text-xs">
                      {betragNum > 0 ? monatlich.toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €' : ''}
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot className="bg-gray-50 border-t border-gray-200">
              <tr>
                <td colSpan={3} className="px-4 py-2.5 font-medium text-gray-700">Gesamt</td>
                <td className="px-4 py-2.5 text-right font-bold text-gray-900">
                  {gesamtSumme.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                </td>
                <td className="px-4 py-2.5 text-right font-medium text-gray-600">
                  {(gesamtSumme / 12).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                </td>
              </tr>
              <tr>
                <td colSpan={3} className="px-4 py-1 text-xs text-gray-500">davon Hausgeld (lfd.)</td>
                <td className="px-4 py-1 text-right text-xs text-primary-700 font-medium">
                  {hausgeldSumme.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                </td>
                <td className="px-4 py-1 text-right text-xs text-primary-600">
                  {(hausgeldSumme / 12).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onZurueck} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2">
          ← Zurück
        </button>
        <button
          onClick={onWeiter}
          disabled={!wp.positionen || wp.positionen.length === 0}
          className="bg-primary-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-primary-700 disabled:opacity-40"
        >
          Weiter →
        </button>
      </div>
    </div>
  )
}
