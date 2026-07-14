/**
 * Rechnungsfreigabe — Stufe 2 (Umbau v1.1, Spec Kap. 5.2 / 9).
 *
 * Liste aller Rechnungen `zur_freigabe`, für die der eingeloggte User laut
 * objektbasierten zahlungsfreigabe_grenzen zuständig ist. Der Freigeber darf
 * das Sachkonto korrigieren; der Button „Freigabe" (ehem. „Sachkonto
 * speichern") speichert die Korrektur UND schließt die Freigabe ab.
 * Bei geändertem Konto: Match-Regel-Dialog (Ja/Nein) — nur „Ja" lernt.
 */
import { useCallback, useEffect, useState } from 'react'
import { rechnungenApi } from '../../api/rechnungen'
import { buchhaltungApi } from '../../api/buchhaltung'
import type { Konto, RechnungList } from '../../types'
import { Ampelpunkt } from './Ampel'

function istAufwandskonto(k: Konto): boolean {
  const nr = Number(k.kontonummer)
  return k.aktiv && k.kontoart !== 'summierung' && (k.direktes_buchen || (nr >= 50000 && nr <= 55999))
}

export default function RechnungsFreigabe() {
  const [rows, setRows] = useState<RechnungList[]>([])
  const [kontenByObjekt, setKontenByObjekt] = useState<Record<string, Konto[]>>({})
  const [auswahl, setAuswahl] = useState<Record<string, string>>({})   // rechnungId → kontoId
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)

  const laden = useCallback(() => {
    setLoading(true)
    rechnungenApi.freigabeListe()
      .then(data => {
        setRows(data)
        setAuswahl(Object.fromEntries(data.map(r => [r.id, r.aufwandskonto_id ?? ''])))
        // Aufwandskonten je Objekt einmalig laden
        const objektIds = [...new Set(data.map(r => r.objekt_id).filter((x): x is string => !!x))]
        objektIds.forEach(oid => {
          buchhaltungApi.konten(oid)
            .then(ks => setKontenByObjekt(prev => ({ ...prev, [oid]: ks.filter(istAufwandskonto) })))
            .catch(() => {})
        })
      })
      .catch(() => setFehler('Freigabe-Liste konnte nicht geladen werden.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { laden() }, [laden])

  const freigeben = async (r: RechnungList) => {
    const kontoId = auswahl[r.id]
    const geaendert = !!kontoId && kontoId !== (r.aufwandskonto_id ?? '')
    let lernen = false
    if (geaendert) {
      // Match-Regel-Rückfrage (Spec 5.3) — nur „Ja" aktualisiert die Regel
      lernen = window.confirm(
        'Zuordnung geändert — Match-Regel für künftige Rechnungen dieses '
        + 'Kreditors aktualisieren?\n\nOK = Ja, Regel aktualisieren · Abbrechen = Nein, nur diese Rechnung',
      )
    }
    setBusyId(r.id); setFehler(null)
    try {
      await rechnungenApi.freigeben(r.id, {
        ...(geaendert ? { aufwandskonto_id: kontoId, lernen } : {}),
      })
      laden()
    } catch (e) {
      const msg = (e as { response?: { data?: { error?: string } } }).response?.data?.error
      setFehler(msg ?? 'Freigabe fehlgeschlagen.')
    } finally { setBusyId(null) }
  }

  const ablehnen = async (r: RechnungList) => {
    const grund = window.prompt('Begründung der Ablehnung:')
    if (grund == null) return
    await rechnungenApi.ablehnen(r.id, grund)
    laden()
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-gray-800 mb-4">Rechnungsfreigabe — Stufe 2</h1>
      {fehler && <div className="mb-3 text-sm text-red-600">{fehler}</div>}
      {loading ? (
        <div className="text-gray-500 text-sm">Lädt…</div>
      ) : rows.length === 0 ? (
        <div className="text-gray-500 text-sm">Keine Rechnungen zur Freigabe.</div>
      ) : (
        <div className="overflow-x-auto border rounded">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-3 py-2 text-left">Ampel</th>
                <th className="px-3 py-2 text-left">Kreditor</th>
                <th className="px-3 py-2 text-left">Rechnungs-Nr.</th>
                <th className="px-3 py-2 text-left">Objekt</th>
                <th className="px-3 py-2 text-right">Betrag</th>
                <th className="px-3 py-2 text-left">Sachkonto (korrigierbar)</th>
                <th className="px-3 py-2 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const konten = r.objekt_id ? (kontenByObjekt[r.objekt_id] ?? []) : []
                const geaendert = !!auswahl[r.id] && auswahl[r.id] !== (r.aufwandskonto_id ?? '')
                return (
                  <tr key={r.id} className="border-t hover:bg-gray-50">
                    <td className="px-3 py-2"><Ampelpunkt ampel={r.erkennung_ampel} /></td>
                    <td className="px-3 py-2">{r.kreditor_name || r.lieferant_name || '—'}</td>
                    <td className="px-3 py-2 font-mono text-gray-600">{r.rechnungsnummer || '—'}</td>
                    <td className="px-3 py-2 text-gray-600">{r.objekt_bezeichnung ?? '—'}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {r.betrag_brutto ? `${Number(r.betrag_brutto).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €` : '—'}
                    </td>
                    <td className="px-3 py-2">
                      <select
                        className={`border rounded px-2 py-1 text-sm w-64 ${geaendert ? 'border-amber-400 bg-amber-50' : ''}`}
                        value={auswahl[r.id] ?? ''}
                        onChange={e => setAuswahl(prev => ({ ...prev, [r.id]: e.target.value }))}
                      >
                        <option value="">— Konto wählen —</option>
                        {konten.map(k => (
                          <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>
                        ))}
                      </select>
                      {geaendert && (
                        <span className="block text-xs text-amber-700 mt-0.5">Konto geändert — beim Freigeben folgt die Match-Regel-Rückfrage</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      <button onClick={() => rechnungenApi.openPdf(r.id).catch(() => {})}
                              className="text-blue-600 hover:underline mr-3">PDF</button>
                      <button onClick={() => freigeben(r)} disabled={busyId === r.id}
                              className="px-3 py-1 rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 mr-2">
                        Freigabe
                      </button>
                      <button onClick={() => ablehnen(r)} className="text-red-600 hover:underline">Ablehnen</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
