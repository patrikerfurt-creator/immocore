import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import { wirtschaftsjahreApi } from '../../api/wirtschaftsjahre'
import { useObjektStore } from '../../stores/objekt'
import type { BebuchtesKonto, Wirtschaftsjahr } from '../../types'

const EUR = (v: number | null | undefined) =>
  (v ?? 0).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
const DATUM = (s: string) => new Date(s).toLocaleDateString('de-DE')

export function Kontoauszug() {
  const objektId = useObjektStore(s => s.selectedId)
  const [selected, setSelected] = useState<BebuchtesKonto | null>(null)
  const [selectedWjId, setSelectedWjId] = useState<string | null>(null)

  const { data: wirtschaftsjahre = [], isLoading: wjLaden } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => wirtschaftsjahreApi.list({ objekt: objektId! }),
    enabled: !!objektId,
    select: (wjs: Wirtschaftsjahr[]) => [...wjs].sort((a, b) => b.jahr - a.jahr),
  })

  const aktivesWj: Wirtschaftsjahr | undefined = (() => {
    if (!wirtschaftsjahre.length) return undefined
    if (selectedWjId) return wirtschaftsjahre.find(w => w.id === selectedWjId)
    return wirtschaftsjahre.find(w => w.status === 'offen') ?? wirtschaftsjahre[0]
  })()

  if (!objektId) {
    return <div className="p-6 text-gray-500">Bitte zuerst ein Objekt auswählen.</div>
  }

  const wjSelector = (
    <div className="flex items-center gap-2">
      {wjLaden ? (
        <span className="text-sm text-gray-400">Lade WJ…</span>
      ) : wirtschaftsjahre.length > 0 ? (
        <>
          <span className="text-sm text-gray-500 font-medium">Wirtschaftsjahr:</span>
          <select
            value={aktivesWj?.id ?? ''}
            onChange={e => { setSelectedWjId(e.target.value || null); setSelected(null) }}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {wirtschaftsjahre.map(wj => (
              <option key={wj.id} value={wj.id}>
                {wj.jahr}{wj.status === 'abgeschlossen' ? ' (abgeschlossen)' : ''}
              </option>
            ))}
          </select>
        </>
      ) : null}
    </div>
  )

  return (
    <div>
      {selected ? (
        <KontoDetail
          konto={selected}
          wjId={aktivesWj?.id}
          onBack={() => setSelected(null)}
          wjSelector={wjSelector}
        />
      ) : (
        <KontenListe
          objektId={objektId}
          wjId={aktivesWj?.id}
          wjLaden={wjLaden}
          onSelect={setSelected}
          wjSelector={wjSelector}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ebene 1: Bebuchte Konten
// ---------------------------------------------------------------------------

function KontenListe({
  objektId,
  wjId,
  wjLaden,
  onSelect,
  wjSelector,
}: {
  objektId: string
  wjId: string | undefined
  wjLaden: boolean
  onSelect: (k: BebuchtesKonto) => void
  wjSelector: React.ReactNode
}) {
  const { data: konten, isLoading } = useQuery({
    queryKey: ['bebuchte-konten', objektId, wjId ?? 'alle'],
    queryFn: () => buchhaltungApi.bebuchteKonten(objektId, wjId ? { wirtschaftsjahr: wjId } : undefined),
    enabled: !wjLaden,
  })

  const gruppen = gruppiereNachBereich(konten ?? [])

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Kontoauszug / Sachkonten</h1>
        <div className="flex items-center gap-4">
          {wjSelector}
          <div className="text-sm text-gray-400">{(konten ?? []).length} bebuchte Konten</div>
        </div>
      </div>

      {isLoading ? (
        <div className="text-gray-500 text-sm">Lade Konten…</div>
      ) : (konten ?? []).length === 0 ? (
        <div className="bg-white rounded-lg border p-8 text-center text-gray-400">
          Keine Buchungen vorhanden
        </div>
      ) : (
        <div className="space-y-4">
          {gruppen.map(gruppe => (
            <div key={gruppe.label} className="bg-white rounded-lg border overflow-hidden">
              <div className="px-4 py-2.5 bg-gray-100 border-b">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {gruppe.label}
                </span>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-gray-600 font-medium w-24">Konto</th>
                    <th className="text-left px-4 py-2.5 text-gray-600 font-medium">Bezeichnung</th>
                    <th className="text-right px-4 py-2.5 text-gray-600 font-medium w-32">Soll</th>
                    <th className="text-right px-4 py-2.5 text-gray-600 font-medium w-32">Haben</th>
                    <th className="text-right px-4 py-2.5 text-gray-600 font-medium w-32">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {gruppe.konten.map(k => (
                    <tr
                      key={k.id}
                      onClick={() => onSelect(k)}
                      className="border-t hover:bg-blue-50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-2.5 font-mono font-semibold text-blue-700">
                        {k.kontonummer}
                      </td>
                      <td className="px-4 py-2.5 text-gray-800">{k.kontoname}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">
                        {k.soll_summe !== 0 ? EUR(k.soll_summe) : ''}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">
                        {k.haben_summe !== 0 ? EUR(k.haben_summe) : ''}
                      </td>
                      <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${
                        k.saldo > 0 ? 'text-gray-800'
                        : k.saldo < 0 ? 'text-blue-700'
                        : 'text-gray-400'
                      }`}>
                        {EUR(Math.abs(k.saldo))}
                        <span className="text-xs font-normal text-gray-400 ml-1">
                          {k.saldo > 0 ? 'S' : k.saldo < 0 ? 'H' : ''}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ebene 2: Buchungen eines Kontos
// ---------------------------------------------------------------------------

function KontoDetail({
  konto,
  wjId,
  onBack,
  wjSelector,
}: {
  konto: BebuchtesKonto
  wjId: string | undefined
  onBack: () => void
  wjSelector: React.ReactNode
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['sachkonto-auszug', konto.id, wjId ?? 'alle'],
    queryFn: () => buchhaltungApi.sachkontoAuszug(konto.id, wjId ? { wirtschaftsjahr: wjId } : undefined),
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-sm text-blue-600 hover:underline"
        >
          ← Zurück zur Kontenübersicht
        </button>
        {wjSelector}
      </div>

      {/* Konto-Header */}
      <div className="bg-white rounded-lg border p-5 mb-4">
        <div className="flex justify-between items-start">
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Sachkonto</div>
            <h2 className="text-xl font-bold text-gray-900">
              <span className="font-mono text-blue-700 mr-3">{konto.kontonummer}</span>
              {konto.kontoname}
            </h2>
            {konto.abrechnungsart && (
              <div className="text-sm text-gray-400 mt-1">
                Abrechnungsart {konto.abrechnungsart}
              </div>
            )}
          </div>
          <div className="text-right space-y-1">
            <div>
              <div className="text-xs text-gray-400">Soll</div>
              <div className="font-semibold tabular-nums text-gray-700">{EUR(konto.soll_summe)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Haben</div>
              <div className="font-semibold tabular-nums text-gray-700">{EUR(konto.haben_summe)}</div>
            </div>
            <div className="border-t pt-1">
              <div className="text-xs text-gray-400">Saldo</div>
              <div className={`font-bold tabular-nums text-lg ${
                (data?.saldo_gesamt ?? konto.saldo) > 0 ? 'text-gray-800' : 'text-blue-700'
              }`}>
                {EUR(Math.abs(data?.saldo_gesamt ?? konto.saldo))}
                <span className="text-xs font-normal text-gray-400 ml-1">
                  {(data?.saldo_gesamt ?? konto.saldo) > 0 ? 'Soll' : 'Haben'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Buchungstabelle */}
      {isLoading ? (
        <div className="text-gray-500 text-sm">Lade Kontoauszug…</div>
      ) : (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-600 font-medium w-36">BU-Nr.</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium w-28">BU-Datum</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium w-40">Gegenkonto</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium">Text</th>
                <th className="text-right px-4 py-3 text-gray-600 font-medium w-28">Soll</th>
                <th className="text-right px-4 py-3 text-gray-600 font-medium w-28">Haben</th>
                <th className="text-right px-4 py-3 text-gray-600 font-medium w-28">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {(data?.positionen ?? []).length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-gray-400">
                    Keine Buchungen vorhanden
                  </td>
                </tr>
              ) : (data?.positionen ?? []).map(pos => (
                <tr key={pos.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{pos.bu_nr}</td>
                  <td className="px-4 py-2.5 text-gray-700 whitespace-nowrap">{DATUM(pos.buchungsdatum)}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-600 truncate max-w-0">
                    {pos.gegenkonto}
                  </td>
                  <td className="px-4 py-2.5 text-gray-800 truncate max-w-xs">{pos.buchungstext || '—'}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-gray-800">
                    {pos.soll != null ? EUR(pos.soll) : ''}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-blue-700">
                    {pos.haben != null ? EUR(pos.haben) : ''}
                  </td>
                  <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${
                    pos.saldo > 0 ? 'text-gray-800' : pos.saldo < 0 ? 'text-blue-700' : 'text-gray-400'
                  }`}>
                    {EUR(Math.abs(pos.saldo))}
                    <span className="text-xs font-normal text-gray-400 ml-0.5">
                      {pos.saldo > 0 ? 'S' : pos.saldo < 0 ? 'H' : ''}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
            {(data?.positionen ?? []).length > 0 && (
              <tfoot className="bg-gray-50 border-t-2 border-gray-300">
                <tr>
                  <td colSpan={4} className="px-4 py-3 text-right font-semibold text-gray-700">
                    Abschlusssaldo
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-bold text-gray-800">
                    {(data?.saldo_gesamt ?? 0) > 0 ? EUR(data?.saldo_gesamt ?? 0) : ''}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-bold text-blue-700">
                    {(data?.saldo_gesamt ?? 0) < 0 ? EUR(Math.abs(data?.saldo_gesamt ?? 0)) : ''}
                  </td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hilfsfunktion: Konten nach Kontenbereich gruppieren
// ---------------------------------------------------------------------------

function gruppiereNachBereich(konten: BebuchtesKonto[]) {
  const bereiche: { label: string; prefix: string }[] = [
    { label: 'Anlagevermögen (0xxx)', prefix: '0' },
    { label: 'Umlaufvermögen / Forderungen (1xxx)', prefix: '1' },
    { label: 'Eigenkapital / Rücklagen (2xxx)', prefix: '2' },
    { label: 'Verbindlichkeiten (3xxx)', prefix: '3' },
    { label: 'Erlöse / Hausgeld (4xxx)', prefix: '4' },
    { label: 'Aufwendungen Verwaltung (5xxx)', prefix: '5' },
    { label: 'Aufwendungen Bewirtschaftung (6xxx)', prefix: '6' },
    { label: 'Sonstige Aufwendungen (7xxx)', prefix: '7' },
    { label: 'Neutrale / Sonstige (8xxx)', prefix: '8' },
    { label: 'Statistik / Verrechnungskonten (9xxx)', prefix: '9' },
  ]

  return bereiche
    .map(b => ({
      label: b.label,
      konten: konten.filter(k => k.kontonummer.startsWith(b.prefix)),
    }))
    .filter(g => g.konten.length > 0)
}
