/**
 * Rechnungsfreigabe — Stufe 2 (Umbau v1.1, Spec Kap. 5.2 / 9).
 *
 * Liste aller Rechnungen `zur_freigabe`, für die der eingeloggte User laut
 * objektbasierten zahlungsfreigabe_grenzen zuständig ist. Der Freigeber darf
 * das Sachkonto korrigieren; der Button „Freigabe" (ehem. „Sachkonto
 * speichern") speichert die Korrektur UND schließt die Freigabe ab.
 * Bei geändertem Konto: Match-Regel-Dialog (Ja/Nein) — nur „Ja" lernt.
 *
 * Zweiter Block: eingereichte WKZ-Vorlagen (wiederkehrende Zahlungen). Eine aus
 * einem Beleg angelegte WKZ nimmt die Rechnung aus dem normalen Zahlweg —
 * freigegeben wird deshalb hier die Vorlage (Bewertung über den Jahresbetrag).
 */
import { useCallback, useEffect, useState } from 'react'
import { rechnungenApi } from '../../api/rechnungen'
import { buchhaltungApi } from '../../api/buchhaltung'
import { wkzApi, type WKZVorlageFreigabe } from '../../api/wkz'
import type { Konto, RechnungList } from '../../types'
import { Ampelpunkt } from './Ampel'

const RHYTHMUS_LABEL: Record<string, string> = {
  monatlich: 'monatlich',
  zweimonatlich: 'zweimonatlich',
  quartalsweise: 'quartalsweise',
  halbjaehrlich: 'halbjährlich',
  jaehrlich: 'jährlich',
  frei: 'frei (manuell)',
}

function eur(wert: string | null): string {
  if (wert == null) return '—'
  return `${Number(wert).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €`
}

// Konten werden je Objekt UND Wirtschaftsjahr vorgehalten — dieselbe Kontonummer
// existiert pro Jahr einmal, und ein Beleg braucht das Konto seines Jahres.
function schluessel(objektId: string, jahr: string): string {
  return `${objektId}|${jahr}`
}

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
  const [kontenFehler, setKontenFehler] = useState<string | null>(null)
  const [wkzRows, setWkzRows] = useState<WKZVorlageFreigabe[]>([])
  const [wkzFehler, setWkzFehler] = useState<string | null>(null)

  const laden = useCallback(() => {
    setLoading(true)
    setKontenFehler(null)
    rechnungenApi.freigabeListe()
      .then(data => {
        setRows(data)
        setAuswahl(Object.fromEntries(data.map(r => [r.id, r.aufwandskonto_id ?? ''])))
        // Aufwandskonten je Objekt UND Rechnungsjahr laden.
        // Konten sind jahresgebunden: ohne Jahr liefert die API die Konten des
        // laufenden Wirtschaftsjahres, waehrend die Vorkontierung auf das Konto
        // des Belegjahres zeigt. Das <select> faende seinen Wert dann nicht.
        const kombis = new Map<string, { oid: string; jahr: string }>()
        data.forEach(r => {
          if (!r.objekt_id) return
          const jahr = /^\d{4}-/.test(r.rechnungsdatum ?? '') ? r.rechnungsdatum!.slice(0, 4) : ''
          kombis.set(schluessel(r.objekt_id, jahr), { oid: r.objekt_id, jahr })
        })
        kombis.forEach(({ oid, jahr }, key) => {
          buchhaltungApi.konten(oid, jahr ? { jahr } : undefined)
            .then(ks => setKontenByObjekt(prev => ({ ...prev, [key]: ks.filter(istAufwandskonto) })))
            // Fehler nicht verschlucken: ohne Hinweis sieht ein fehlgeschlagener
            // Request genauso aus wie eine leere Kontenliste.
            .catch(() => setKontenFehler(
              `Aufwandskonten konnten nicht geladen werden${jahr ? ` (Wirtschaftsjahr ${jahr})` : ''}. `
              + 'Die Kontoauswahl bleibt leer — bitte die Seite neu laden.'))
        })
      })
      .catch(() => setFehler('Freigabe-Liste konnte nicht geladen werden.'))
      .finally(() => setLoading(false))
  }, [])

  const wkzLaden = useCallback(() => {
    wkzApi.freigabeListe()
      .then(setWkzRows)
      .catch(() => setWkzFehler('WKZ-Freigabeliste konnte nicht geladen werden.'))
  }, [])

  useEffect(() => { laden(); wkzLaden() }, [laden, wkzLaden])

  const wkzFreigeben = async (v: WKZVorlageFreigabe) => {
    setBusyId(v.id); setWkzFehler(null)
    try {
      await wkzApi.vorlageFreigeben(v.id)
      wkzLaden()
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setWkzFehler(msg ?? 'Freigabe der WKZ-Vorlage fehlgeschlagen.')
    } finally { setBusyId(null) }
  }

  const wkzAblehnen = async (v: WKZVorlageFreigabe) => {
    const grund = window.prompt('Begründung der Ablehnung (Vorlage geht zurück in den Entwurf):')
    if (grund == null) return
    setBusyId(v.id); setWkzFehler(null)
    try {
      await wkzApi.vorlageAblehnen(v.id, grund)
      wkzLaden()
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setWkzFehler(msg ?? 'Ablehnen fehlgeschlagen.')
    } finally { setBusyId(null) }
  }

  const freigeben = async (r: RechnungList) => {
    const kontoId = auswahl[r.id]
    // v1_1: ohne Aufwandskonto (weder gewählt noch gespeichert) ist keine Freigabe möglich
    if (!kontoId && !r.aufwandskonto_id) {
      setFehler('Bitte zuerst ein Aufwandskonto wählen.')
      return
    }
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
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">Rechnungen</h2>
      {fehler && <div className="mb-3 text-sm text-red-600">{fehler}</div>}
      {kontenFehler && (
        <div className="mb-3 p-2.5 rounded bg-red-50 border border-red-200 text-sm text-red-700">
          ⚠ {kontenFehler}
        </div>
      )}
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
                const rJahr = /^\d{4}-/.test(r.rechnungsdatum ?? '') ? r.rechnungsdatum!.slice(0, 4) : ''
                const konten = r.objekt_id ? (kontenByObjekt[schluessel(r.objekt_id, rJahr)] ?? []) : []
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

      {/* ------------------------------------------------------------------ */}
      {/* WKZ — wiederkehrende Zahlungen (aus Belegen angelegt)              */}
      {/* ------------------------------------------------------------------ */}
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mt-8 mb-2">
        Wiederkehrende Zahlungen (WKZ)
      </h2>
      <p className="text-xs text-gray-500 mb-2">
        Vorlagen aus einer Eingangsrechnung: die Zahlung läuft über die wiederkehrende Zahlung
        statt über die einzelne Rechnung — freigegeben wird deshalb hier die Vorlage
        (Bewertung über den Jahresbetrag).
      </p>
      {wkzFehler && <div className="mb-3 text-sm text-red-600">{wkzFehler}</div>}
      {wkzRows.length === 0 ? (
        <div className="text-gray-500 text-sm">Keine wiederkehrenden Zahlungen zur Freigabe.</div>
      ) : (
        <div className="overflow-x-auto border rounded">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-3 py-2 text-left">Kreditor</th>
                <th className="px-3 py-2 text-left">Bezeichnung</th>
                <th className="px-3 py-2 text-left">Objekt</th>
                <th className="px-3 py-2 text-left">Rhythmus / Zahlweg</th>
                <th className="px-3 py-2 text-right">Betrag je Periode</th>
                <th className="px-3 py-2 text-right">Jahresbetrag</th>
                <th className="px-3 py-2 text-left">Sachkonten</th>
                <th className="px-3 py-2 text-left">Beleg</th>
                <th className="px-3 py-2 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {wkzRows.map(v => (
                <tr key={v.id} className="border-t hover:bg-gray-50">
                  <td className="px-3 py-2">{v.kreditor_name}</td>
                  <td className="px-3 py-2">
                    {v.bezeichnung}
                    <span className="block text-xs text-gray-500">
                      {v.typ === 'bescheid' ? 'Bescheid' : 'Vertrag'} · ab {new Date(v.gueltig_ab).toLocaleDateString('de-DE')}
                      {v.erstellt_von_name ? ` · erfasst von ${v.erstellt_von_name}` : ''}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-600">{v.objekt_bezeichnung}</td>
                  <td className="px-3 py-2 text-gray-600">
                    {RHYTHMUS_LABEL[v.rhythmus] ?? v.rhythmus}
                    <span className="block text-xs text-gray-500">
                      {v.zahlweg === 'lastschrift' ? 'Lastschrift' : 'Überweisung'}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{eur(v.betrag_gesamt)}</td>
                  <td className="px-3 py-2 text-right font-mono font-medium">{eur(v.jahresbetrag)}</td>
                  <td className="px-3 py-2 text-xs text-gray-600">
                    {v.splits.map(sp => (
                      <span key={sp.id} className="block font-mono">
                        {sp.kontonummer} · {eur(sp.betrag)}
                      </span>
                    ))}
                  </td>
                  <td className="px-3 py-2">
                    {v.rechnung_id ? (
                      <button onClick={() => rechnungenApi.openPdf(v.rechnung_id!).catch(() => {})}
                              className="text-blue-600 hover:underline">
                        {v.rechnung_nummer || 'PDF'}
                      </button>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button onClick={() => wkzFreigeben(v)} disabled={busyId === v.id}
                            className="px-3 py-1 rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 mr-2">
                      Freigabe
                    </button>
                    <button onClick={() => wkzAblehnen(v)} disabled={busyId === v.id}
                            className="text-red-600 hover:underline">Ablehnen</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
