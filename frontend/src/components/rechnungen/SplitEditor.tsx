/**
 * SplitEditor — Aufteilen einer Rechnung auf mehrere Aufwandskonten.
 *
 * Props:
 *   rechnungId    — UUID der Rechnung
 *   betragBrutto  — Gesamtbetrag (string | null)
 *   vorhandene    — bereits gespeicherte Splits (aus rechnung.splits)
 *   konten        — verfügbare Aufwandskonten (gefiltert nach Objekt)
 *   onSaved       — Callback nach erfolgreichem Speichern
 *   onGeloescht   — Callback nach Löschen aller Splits
 */
import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { rechnungenApi } from '../../api/rechnungen'
import type { Konto, RechnungSplitPosition } from '../../types'
import { Button } from '../ui/Button'

const EUR = (v: string | number | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

interface SplitRow {
  aufwandskonto: string
  betrag: string
}

interface Props {
  rechnungId: string
  betragBrutto: string | null
  vorhandene: RechnungSplitPosition[]
  konten: Konto[]
  onSaved?: () => void
  onGeloescht?: () => void
}

export function SplitEditor({ rechnungId, betragBrutto, vorhandene, konten, onSaved, onGeloescht }: Props) {
  const qc = useQueryClient()

  const initialRows = (): SplitRow[] => {
    if (vorhandene.length >= 2) {
      return vorhandene.map(s => ({ aufwandskonto: s.aufwandskonto, betrag: s.betrag }))
    }
    return [
      { aufwandskonto: '', betrag: '' },
      { aufwandskonto: '', betrag: '' },
    ]
  }

  const [rows, setRows] = useState<SplitRow[]>(initialRows)

  // Re-init wenn vorhandene Splits sich ändern (z.B. nach Speichern)
  useEffect(() => {
    if (vorhandene.length >= 2) {
      setRows(vorhandene.map(s => ({ aufwandskonto: s.aufwandskonto, betrag: s.betrag })))
    }
  }, [vorhandene.map(s => s.id).join(',')])

  const gesamt = betragBrutto ? Number(betragBrutto) : null
  const splitSumme = rows.reduce((acc, r) => acc + (parseFloat(r.betrag.replace(',', '.')) || 0), 0)
  const differenz  = gesamt != null ? gesamt - splitSumme : null
  const summePaszt = differenz != null && Math.abs(differenz) < 0.005

  const mutSpeichern = useMutation({
    mutationFn: () => rechnungenApi.splitsSpeichern(
      rechnungId,
      rows.map(r => ({ aufwandskonto: r.aufwandskonto, betrag: r.betrag.replace(',', '.') })),
    ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rechnung', rechnungId] })
      qc.invalidateQueries({ queryKey: ['rechnungen'] })
      onSaved?.()
    },
  })

  const mutLoeschen = useMutation({
    mutationFn: () => rechnungenApi.splitsLoeschen(rechnungId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rechnung', rechnungId] })
      qc.invalidateQueries({ queryKey: ['rechnungen'] })
      setRows([{ aufwandskonto: '', betrag: '' }, { aufwandskonto: '', betrag: '' }])
      onGeloescht?.()
    },
  })

  function setRow(i: number, field: keyof SplitRow, value: string) {
    setRows(prev => prev.map((r, idx) => idx === i ? { ...r, [field]: value } : r))
  }

  function addRow() {
    setRows(prev => [...prev, { aufwandskonto: '', betrag: '' }])
  }

  function removeRow(i: number) {
    if (rows.length <= 2) return
    setRows(prev => prev.filter((_, idx) => idx !== i))
  }

  // Differenz auf letzte leere Zeile verteilen
  function restBetragEintragen() {
    if (differenz == null) return
    const letzteLeere = [...rows].reverse().findIndex(r => !r.betrag)
    if (letzteLeere < 0) return
    const idx = rows.length - 1 - letzteLeere
    setRow(idx, 'betrag', Math.abs(differenz).toFixed(2))
  }

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="grid grid-cols-[1fr_120px_28px] gap-1 text-xs text-gray-400 font-medium px-1">
        <span>Aufwandskonto</span>
        <span className="text-right">Betrag</span>
        <span />
      </div>

      {/* Split-Zeilen */}
      {rows.map((row, i) => (
        <div key={i} className="grid grid-cols-[1fr_120px_28px] gap-1 items-center">
          <select
            value={row.aufwandskonto}
            onChange={e => setRow(i, 'aufwandskonto', e.target.value)}
            className="border rounded px-2 py-1 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 w-full"
          >
            <option value="">— Konto wählen —</option>
            {konten.map(k => (
              <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>
            ))}
          </select>
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={row.betrag}
            onChange={e => setRow(i, 'betrag', e.target.value)}
            placeholder="0.00"
            className="border rounded px-2 py-1 text-sm text-right bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 w-full"
          />
          <button
            type="button"
            onClick={() => removeRow(i)}
            disabled={rows.length <= 2}
            className="text-gray-300 hover:text-red-400 disabled:opacity-30 text-lg leading-none"
            title="Zeile entfernen"
          >
            ×
          </button>
        </div>
      ))}

      {/* Summenzeile */}
      <div className={`flex justify-between items-center text-xs px-1 pt-1 border-t ${summePaszt ? 'text-green-700' : 'text-orange-600'}`}>
        <span>
          Summe: <strong>{EUR(splitSumme.toFixed(2))}</strong>
          {gesamt != null && (
            <span className="ml-2 text-gray-400">
              von {EUR(betragBrutto)}
            </span>
          )}
        </span>
        {differenz != null && !summePaszt && (
          <button
            type="button"
            onClick={restBetragEintragen}
            className="text-xs text-blue-600 hover:underline ml-2"
            title="Differenz auf letzte leere Zeile eintragen"
          >
            Restbetrag eintragen ({EUR(Math.abs(differenz).toFixed(2))})
          </button>
        )}
        {summePaszt && <span className="text-green-600">✓ passt</span>}
      </div>

      {/* Aktionen */}
      <div className="flex items-center gap-2 flex-wrap pt-1">
        <button
          type="button"
          onClick={addRow}
          className="text-xs text-blue-600 hover:underline"
        >
          + Zeile hinzufügen
        </button>
        <div className="flex-1" />
        {vorhandene.length >= 2 && (
          <button
            type="button"
            onClick={() => mutLoeschen.mutate()}
            disabled={mutLoeschen.isPending}
            className="text-xs text-gray-400 hover:text-red-500"
          >
            {mutLoeschen.isPending ? '…' : 'Splits löschen'}
          </button>
        )}
        <Button
          onClick={() => mutSpeichern.mutate()}
          disabled={!summePaszt || rows.some(r => !r.aufwandskonto || !r.betrag) || mutSpeichern.isPending}
        >
          {mutSpeichern.isPending ? 'Speichert…' : 'Splits speichern'}
        </Button>
      </div>

      {mutSpeichern.isError && (
        <div className="text-xs text-red-600">
          {(mutSpeichern.error as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Fehler beim Speichern.'}
        </div>
      )}
      {mutSpeichern.isSuccess && (
        <div className="text-xs text-green-600">✓ Splits gespeichert</div>
      )}
    </div>
  )
}
