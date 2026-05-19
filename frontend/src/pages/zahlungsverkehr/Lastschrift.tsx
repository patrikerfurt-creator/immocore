import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useObjektStore } from '../../stores/objekt'
import { zahlungsverkehrApi } from '../../api/zahlungsverkehr'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { LastschriftLauf, HausgeldSollstellungslauf } from '../../types'


function formatEuro(val: string | number | null | undefined) {
  if (val == null) return '—'
  return Number(val).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

function formatDatum(s: string | null | undefined) {
  if (!s) return '—'
  const [y, m, d] = s.split('-')
  return `${d}.${m}.${y}`
}

export function Lastschrift() {
  const objektId = useObjektStore(s => s.selectedId)
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [hgLaufId, setHgLaufId] = useState('')
  const [faelligkeitsdatum, setFaelligkeitsdatum] = useState('')
  const [bezeichnung, setBezeichnung] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: laeufe, isLoading } = useQuery({
    queryKey: ['lastschrift-laeufe', objektId],
    queryFn: () => zahlungsverkehrApi.lastschriftLaeufe(objektId ? { objekt: objektId } : {}),
    enabled: !!objektId,
  })

  const { data: hgLaeufe } = useQuery({
    queryKey: ['hg-laeufe', objektId, 'commited'],
    queryFn: () => zahlungsverkehrApi.hausgeldLaeufe(objektId ? { objekt: objektId, status: 'commited' } : {}),
    enabled: !!objektId && showForm,
  })

  const erstellenMut = useMutation({
    mutationFn: zahlungsverkehrApi.createLastschriftLauf,
    onSuccess: () => {
      setShowForm(false)
      setHgLaufId('')
      setFaelligkeitsdatum('')
      setBezeichnung('')
      setError(null)
      qc.invalidateQueries({ queryKey: ['lastschrift-laeufe'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg || 'Fehler beim Erstellen')
    },
  })

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      zahlungsverkehrApi.patchLastschriftLauf(id, { status } as Partial<LastschriftLauf>),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lastschrift-laeufe'] }),
  })

  function handleErstellen() {
    if (!objektId || !faelligkeitsdatum) return
    setError(null)
    erstellenMut.mutate({
      objekt_id: objektId,
      hg_lauf_id: hgLaufId || undefined,
      faelligkeitsdatum,
      bezeichnung,
    })
  }

  const commitedHgLaeufe = hgLaeufe ?? []

  if (!objektId) {
    return (
      <div className="p-8 text-gray-500">Bitte ein Objekt auswählen.</div>
    )
  }

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Lastschriften</h1>
        <Button onClick={() => { setShowForm(v => !v); setError(null) }}>
          {showForm ? 'Abbrechen' : '+ Neuer Lauf'}
        </Button>
      </div>

      {showForm && (
        <div className="bg-white border rounded-lg p-5 mb-6 shadow-sm">
          <h2 className="font-medium mb-4">Neuer Lastschrift-Lauf</h2>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Hausgeld-Lauf (optional, nur commited)
              </label>
              <select
                className="w-full border rounded px-3 py-2 text-sm"
                value={hgLaufId}
                onChange={e => setHgLaufId(e.target.value)}
              >
                <option value="">— keiner —</option>
                {commitedHgLaeufe.map((l: HausgeldSollstellungslauf) => (
                  <option key={l.id} value={l.id}>
                    {l.periode ? new Date(l.periode + 'T12:00:00').toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' }) : l.periode} |{' '}
                    {formatEuro(l.summe)} | {l.anzahl_sollstellungen} EV
                  </option>
                ))}
              </select>
              {commitedHgLaeufe.length === 0 && (
                <p className="text-xs text-gray-400 mt-1">Kein committeter Hausgeld-Lauf vorhanden</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Fälligkeitsdatum *
              </label>
              <input
                type="date"
                className="w-full border rounded px-3 py-2 text-sm"
                value={faelligkeitsdatum}
                onChange={e => setFaelligkeitsdatum(e.target.value)}
              />
            </div>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Bezeichnung (optional)
            </label>
            <input
              type="text"
              className="w-full border rounded px-3 py-2 text-sm"
              placeholder="z.B. Hausgeld Januar 2026"
              value={bezeichnung}
              onChange={e => setBezeichnung(e.target.value)}
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm mb-4">
              {error}
            </div>
          )}

          <Button
            onClick={handleErstellen}
            disabled={!faelligkeitsdatum || erstellenMut.isPending}
          >
            {erstellenMut.isPending ? 'Wird erstellt…' : 'Lauf erstellen'}
          </Button>
        </div>
      )}

      {isLoading && <p className="text-gray-500 text-sm">Wird geladen…</p>}

      {!isLoading && (!laeufe || laeufe.length === 0) && (
        <p className="text-gray-500 text-sm">Noch keine Lastschrift-Läufe vorhanden.</p>
      )}

      {laeufe && laeufe.length > 0 && (
        <div className="bg-white border rounded-lg overflow-hidden shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Bezeichnung</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Fälligkeit</th>
                <th className="px-4 py-3 text-right font-medium text-gray-700">Positionen</th>
                <th className="px-4 py-3 text-right font-medium text-gray-700">Gesamt</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Status</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Erstellt am</th>
                <th className="px-4 py-3 text-right font-medium text-gray-700">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {laeufe.map((lauf: LastschriftLauf) => (
                <LaufZeile
                  key={lauf.id}
                  lauf={lauf}
                  onDownload={() =>
                    zahlungsverkehrApi.downloadLastschriftXml(
                      lauf.id,
                      `lastschrift_${lauf.faelligkeitsdatum.replace(/-/g, '')}.xml`
                    )
                  }
                  onEingereicht={() => statusMut.mutate({ id: lauf.id, status: 'eingereicht' })}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function LaufZeile({
  lauf,
  onDownload,
  onEingereicht,
}: {
  lauf: LastschriftLauf
  onDownload: () => void
  onEingereicht: () => void
}) {
  const [showDetail, setShowDetail] = useState(false)

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer"
        onClick={() => setShowDetail(v => !v)}
      >
        <td className="px-4 py-3 font-medium">{lauf.bezeichnung || '—'}</td>
        <td className="px-4 py-3">{formatDatum(lauf.faelligkeitsdatum)}</td>
        <td className="px-4 py-3 text-right">{lauf.anzahl_positionen}</td>
        <td className="px-4 py-3 text-right font-mono">{formatEuro(lauf.gesamt_summe)}</td>
        <td className="px-4 py-3">
          <Badge value={lauf.status} />
        </td>
        <td className="px-4 py-3 text-gray-500">
          {new Date(lauf.erstellt_am).toLocaleDateString('de-DE')}
        </td>
        <td className="px-4 py-3 text-right space-x-2" onClick={e => e.stopPropagation()}>
          <Button variant="secondary" onClick={onDownload}>
            XML herunterladen
          </Button>
          {lauf.status === 'exportiert' && (
            <Button variant="secondary" onClick={onEingereicht}>
              Als eingereicht markieren
            </Button>
          )}
        </td>
      </tr>

      {showDetail && (
        <tr>
          <td colSpan={7} className="px-4 py-4 bg-gray-50">
            <DetailBlock lauf={lauf} />
          </td>
        </tr>
      )}
    </>
  )
}

function DetailBlock({ lauf }: { lauf: LastschriftLauf }) {
  return (
    <div className="space-y-5">

      {/* Protokoll-Header */}
      <div className="bg-white border rounded-lg p-4 text-sm">
        <h3 className="font-semibold text-gray-800 mb-3">Lastschrift-Protokoll</h3>
        <div className="grid grid-cols-3 gap-4 text-xs">
          <div>
            <span className="text-gray-500 block">Objekt</span>
            <span className="font-medium">{lauf.objekt_bezeichnung}</span>
          </div>
          <div>
            <span className="text-gray-500 block">Fälligkeitsdatum</span>
            <span className="font-medium">{formatDatum(lauf.faelligkeitsdatum)}</span>
          </div>
          <div>
            <span className="text-gray-500 block">Gesamtbetrag</span>
            <span className="font-semibold text-base">{formatEuro(lauf.gesamt_summe)}</span>
          </div>
          <div>
            <span className="text-gray-500 block">Positionen</span>
            <span className="font-medium">{lauf.anzahl_positionen} Eigentümer</span>
          </div>
          <div>
            <span className="text-gray-500 block">Gegenkonto</span>
            <span className="font-medium font-mono">13650 DCL-Debitor</span>
          </div>
          <div>
            <span className="text-gray-500 block">Buchungen</span>
            {lauf.buchungen_erstellt ? (
              <span className="text-green-700 font-medium">
                Erstellt am {formatDatum(lauf.buchungen_datum)}
              </span>
            ) : (
              <span className="text-amber-600">Noch nicht erstellt (beim XML-Download)</span>
            )}
          </div>
        </div>
        {lauf.hausgeld_lauf_info && (
          <div className="mt-3 pt-3 border-t text-xs text-gray-500">
            Basis: Hausgeld-Lauf {lauf.hausgeld_lauf_info.periode
              ? new Date(lauf.hausgeld_lauf_info.periode + 'T12:00:00').toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' })
              : lauf.hausgeld_lauf_info.id}
            {' '}({lauf.hausgeld_lauf_info.anzahl_sollstellungen} Sollstellungen)
          </div>
        )}
      </div>

      {/* Positionen-Tabelle */}
      <div>
        <h3 className="text-sm font-medium mb-2">
          Positionen ({lauf.positionen.length})
          {lauf.buchungen_erstellt && (
            <span className="ml-2 text-xs text-green-600 font-normal">— Personenkonten ausgeglichen</span>
          )}
        </h3>
        {lauf.positionen.length > 0 ? (
          <table className="min-w-full text-xs border rounded overflow-hidden">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left">PKto</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-left">IBAN</th>
                <th className="px-3 py-2 text-left">Mandatsref.</th>
                <th className="px-3 py-2 text-right">Betrag</th>
                {lauf.buchungen_erstellt && (
                  <>
                    <th className="px-3 py-2 text-left">Belegnr.</th>
                    <th className="px-3 py-2 text-right">OPOs</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {lauf.positionen.map((p, i) => (
                <tr key={i} className={p.buchung_id ? 'bg-green-50' : ''}>
                  <td className="px-3 py-2 font-mono text-gray-600">{p.personenkonto_nr}</td>
                  <td className="px-3 py-2 font-medium">{p.schuldner_name}</td>
                  <td className="px-3 py-2 font-mono text-gray-600">{p.schuldner_iban}</td>
                  <td className="px-3 py-2 text-gray-600">{p.mandatsreferenz}</td>
                  <td className="px-3 py-2 text-right font-mono font-medium">{formatEuro(p.betrag)}</td>
                  {lauf.buchungen_erstellt && (
                    <>
                      <td className="px-3 py-2 font-mono text-blue-700">{p.belegnr || '—'}</td>
                      <td className="px-3 py-2 text-right text-gray-600">{p.opos_ausgeglichen ?? 0}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 border-t">
              <tr>
                <td colSpan={lauf.buchungen_erstellt ? 4 : 4} className="px-3 py-2 font-medium text-xs text-gray-600">
                  Gesamt
                </td>
                <td className="px-3 py-2 text-right font-mono font-semibold">
                  {formatEuro(lauf.gesamt_summe)}
                </td>
                {lauf.buchungen_erstellt && (
                  <>
                    <td />
                    <td className="px-3 py-2 text-right font-medium">
                      {lauf.positionen.reduce((s, p) => s + (p.opos_ausgeglichen ?? 0), 0)}
                    </td>
                  </>
                )}
              </tr>
            </tfoot>
          </table>
        ) : (
          <p className="text-gray-400 text-xs">Keine Positionen</p>
        )}
      </div>

      {lauf.ohne_mandat.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-amber-700 mb-2">
            Ohne SEPA-Mandat ({lauf.ohne_mandat.length})
          </h3>
          <ul className="text-xs space-y-1">
            {lauf.ohne_mandat.map((o, i) => (
              <li key={i} className="text-amber-700">
                {o.person_name || 'Unbekannt'} (PKto {(o as {personenkonto_nr?: string}).personenkonto_nr || '?'}): {o.grund}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
