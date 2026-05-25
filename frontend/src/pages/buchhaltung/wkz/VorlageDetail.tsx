import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wkzApi, type WKZOP } from '../../../api/wkz'
import { Badge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'

const EUR = (v: string | number | null) =>
  v !== null ? Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }) : '–'

const DATUM = (s: string | null) =>
  s ? new Date(s).toLocaleDateString('de-DE') : '–'

const OP_STATUS_TEXT: Record<string, string> = {
  erzeugt: 'Erzeugt',
  bescheid_fehlt: 'Bescheid fehlt',
  bankabgang_erfolgt: 'Verbucht',
  abweichend_geklaert: 'Abweichend geklärt',
  verworfen: 'Verworfen',
}

// ---------------------------------------------------------------------------
// Beenden-Modal
// ---------------------------------------------------------------------------

function BeendenModal({
  vorlageId,
  onClose,
}: {
  vorlageId: string
  onClose: () => void
}) {
  const [gueltigBis, setGueltigBis] = useState('')
  const [grund, setGrund] = useState('')
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => wkzApi.vorlageBeenden(vorlageId, gueltigBis, grund),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wkz-vorlage', vorlageId] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md space-y-4">
        <h2 className="text-lg font-semibold">Vorlage beenden</h2>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Gültig bis *
          </label>
          <input
            type="date"
            value={gueltigBis}
            onChange={e => setGueltigBis(e.target.value)}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Grund</label>
          <textarea
            value={grund}
            onChange={e => setGrund(e.target.value)}
            rows={2}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          />
        </div>
        {mutation.isError && (
          <p className="text-red-600 text-sm">
            {(mutation.error as Error)?.message ?? 'Fehler'}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>Abbrechen</Button>
          <Button
            variant="primary"
            onClick={() => mutation.mutate()}
            disabled={!gueltigBis || mutation.isPending}
          >
            Beenden
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

export default function VorlageDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const [showBeenden, setShowBeenden] = useState(false)
  const [fehler, setFehler] = useState('')
  const [editMode, setEditMode] = useState(false)
  const [editSplits, setEditSplits] = useState<{ kontonummer: string; bezeichnung: string; betrag: string }[]>([])

  const { data: vorlage, isLoading, error } = useQuery({
    queryKey: ['wkz-vorlage', id],
    queryFn: () => wkzApi.vorlageDetail(id!),
    enabled: !!id,
  })

  const { data: ops = [] } = useQuery({
    queryKey: ['wkz-ops', id],
    queryFn: () => wkzApi.opsJeVorlage(id!),
    enabled: !!id,
  })

  const { data: forecast = [] } = useQuery({
    queryKey: ['wkz-forecast-vorlage', id],
    queryFn: () => wkzApi.vorlageForecast(id!),
    enabled: !!id && vorlage?.status === 'aktiv',
  })

  const einreichenMutation = useMutation({
    mutationFn: () => wkzApi.vorlageEinreichen(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wkz-vorlage', id] }),
    onError: (e: unknown) =>
      setFehler((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Fehler'),
  })

  const freigabenMutation = useMutation({
    mutationFn: () => wkzApi.vorlageFreigeben(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wkz-vorlage', id] }),
    onError: (e: unknown) =>
      setFehler((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Fehler'),
  })

  const bearbeitenMutation = useMutation({
    mutationFn: (splits: typeof editSplits) => {
      const betragGesamt = splits.reduce((s, r) => s + (parseFloat(r.betrag) || 0), 0).toFixed(2)
      return wkzApi.vorlageBearbeiten(id!, {
        splits: splits.map((s, i) => ({ kontonummer: s.kontonummer, bezeichnung: s.bezeichnung, betrag: s.betrag, reihenfolge: i })),
        betrag_gesamt: betragGesamt,
      } as never)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wkz-vorlage', id] })
      setEditMode(false)
      setFehler('')
    },
    onError: (e: unknown) =>
      setFehler((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Fehler beim Speichern'),
  })

  function startEdit() {
    if (!vorlage) return
    setEditSplits(vorlage.splits.map(s => ({ kontonummer: s.kontonummer, bezeichnung: s.bezeichnung, betrag: s.betrag })))
    setEditMode(true)
    setFehler('')
  }

  if (isLoading) return <p className="p-4 text-gray-400">Lade Vorlage…</p>
  if (error || !vorlage) return <p className="p-4 text-red-600">Fehler beim Laden.</p>

  return (
    <div className="p-4 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to=".." className="text-gray-500 hover:text-gray-800 text-sm">
            ← Zurück
          </Link>
          <h1 className="text-xl font-semibold">{vorlage.bezeichnung}</h1>
          <Badge value={vorlage.status} />
        </div>
        <div className="flex gap-2">
          {vorlage.status === 'entwurf' && !editMode && (
            <>
              <Button
                variant="secondary"
                onClick={startEdit}
              >
                Bearbeiten
              </Button>
              <Button
                variant="secondary"
                onClick={() => einreichenMutation.mutate()}
                disabled={einreichenMutation.isPending}
              >
                Einreichen
              </Button>
              <Button
                variant="primary"
                onClick={() => freigabenMutation.mutate()}
                disabled={freigabenMutation.isPending}
              >
                Freigeben
              </Button>
            </>
          )}
          {vorlage.status === 'aktiv' && (
            <Button variant="secondary" onClick={() => setShowBeenden(true)}>
              Beenden
            </Button>
          )}
        </div>
      </div>

      {fehler && <p className="text-red-600 text-sm">{fehler}</p>}

      {/* Stammdaten */}
      <div className="grid grid-cols-2 gap-6 bg-white rounded-lg border border-gray-200 p-5">
        <div className="space-y-3">
          <h2 className="font-medium text-gray-800">Stammdaten</h2>
          <dl className="space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Kreditor</dt>
              <dd>{vorlage.kreditor_name}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Objekt</dt>
              <dd>{vorlage.objekt_bezeichnung}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Typ</dt>
              <dd>{vorlage.typ === 'bescheid' ? 'Bescheid' : 'Vertrag'}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Rhythmus</dt>
              <dd>{vorlage.rhythmus}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Erste Fälligkeit</dt>
              <dd>{DATUM(vorlage.erste_faelligkeit)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Geltung</dt>
              <dd>
                {DATUM(vorlage.gueltig_ab)} – {vorlage.gueltig_bis ? DATUM(vorlage.gueltig_bis) : 'unbefristet'}
              </dd>
            </div>
          </dl>
        </div>
        <div className="space-y-3">
          <h2 className="font-medium text-gray-800">Beträge</h2>
          <dl className="space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Betrag/Periode</dt>
              <dd className="font-medium">{EUR(vorlage.betrag_gesamt)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Jahresbetrag</dt>
              <dd>{EUR(vorlage.jahresbetrag)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Toleranz Betrag</dt>
              <dd>{EUR(vorlage.toleranz_betrag)}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-gray-500 w-36">Toleranz Tage</dt>
              <dd>{vorlage.toleranz_tage} Tage</dd>
            </div>
            {vorlage.sepa_mandat_id && (
              <div className="flex gap-2">
                <dt className="text-gray-500 w-36">SEPA-Mandats-ID</dt>
                <dd className="font-mono text-xs">{vorlage.sepa_mandat_id}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      {/* Splits */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Splits</h2>

        {editMode ? (
          <div className="space-y-3">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500">
                  <th className="pb-2 font-medium w-28">Konto</th>
                  <th className="pb-2 font-medium">Bezeichnung</th>
                  <th className="pb-2 font-medium text-right w-32">Betrag (€)</th>
                  <th className="pb-2 w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {editSplits.map((s, i) => (
                  <tr key={i}>
                    <td className="py-1.5 pr-2">
                      <input
                        className="border rounded px-2 py-1 text-sm font-mono w-full"
                        value={s.kontonummer}
                        maxLength={8}
                        onChange={e => setEditSplits(prev => prev.map((r, j) => j === i ? { ...r, kontonummer: e.target.value } : r))}
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        className="border rounded px-2 py-1 text-sm w-full"
                        value={s.bezeichnung}
                        onChange={e => setEditSplits(prev => prev.map((r, j) => j === i ? { ...r, bezeichnung: e.target.value } : r))}
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="number"
                        step="0.01"
                        className="border rounded px-2 py-1 text-sm text-right w-full"
                        value={s.betrag}
                        onChange={e => setEditSplits(prev => prev.map((r, j) => j === i ? { ...r, betrag: e.target.value } : r))}
                      />
                    </td>
                    <td className="py-1.5 text-center">
                      {editSplits.length > 1 && (
                        <button
                          className="text-red-400 hover:text-red-600 text-lg leading-none"
                          onClick={() => setEditSplits(prev => prev.filter((_, j) => j !== i))}
                        >×</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-gray-300">
                  <td className="pt-2 font-medium" colSpan={2}>Gesamt</td>
                  <td className="pt-2 text-right font-medium tabular-nums">
                    {EUR(editSplits.reduce((s, r) => s + (parseFloat(r.betrag) || 0), 0).toFixed(2))}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>

            <button
              className="text-sm text-blue-600 hover:underline"
              onClick={() => setEditSplits(prev => [...prev, { kontonummer: '', bezeichnung: '', betrag: '0.00' }])}
            >
              + Split hinzufügen
            </button>

            <div className="flex gap-2 pt-1">
              <Button
                onClick={() => bearbeitenMutation.mutate(editSplits)}
                disabled={bearbeitenMutation.isPending}
              >
                {bearbeitenMutation.isPending ? 'Speichere…' : 'Speichern'}
              </Button>
              <Button
                variant="secondary"
                onClick={() => { setEditMode(false); setFehler('') }}
                disabled={bearbeitenMutation.isPending}
              >
                Abbrechen
              </Button>
            </div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="pb-2 font-medium">Konto</th>
                <th className="pb-2 font-medium">Bezeichnung</th>
                <th className="pb-2 font-medium text-right">Betrag</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {vorlage.splits.map(s => (
                <tr key={s.id}>
                  <td className="py-1.5 font-mono">{s.kontonummer}</td>
                  <td className="py-1.5">{s.bezeichnung}</td>
                  <td className="py-1.5 text-right tabular-nums">{EUR(s.betrag)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-gray-300">
                <td className="pt-2 font-medium" colSpan={2}>Gesamt</td>
                <td className="pt-2 text-right font-medium tabular-nums">
                  {EUR(vorlage.betrag_gesamt)}
                </td>
              </tr>
            </tfoot>
          </table>
        )}
      </div>

      {/* Nächste Fälligkeiten (Forecast) */}
      {forecast.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="font-medium text-gray-800 mb-3">Nächste Fälligkeiten</h2>
          <div className="space-y-1 text-sm">
            {forecast.slice(0, 6).map((f, i) => (
              <div key={i} className="flex justify-between text-gray-600">
                <span>{DATUM(f.faellig_am)}</span>
                <span className="text-gray-400 text-xs">
                  {DATUM(f.periode_von)}–{DATUM(f.periode_bis)}
                </span>
                <span className="tabular-nums">{EUR(f.betrag)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Erzeugte OPs */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">
          Erzeugte OPs ({ops.length})
        </h2>
        {ops.length === 0 ? (
          <p className="text-gray-400 text-sm">Noch keine OPs erzeugt.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="pb-2 font-medium">Periode</th>
                <th className="pb-2 font-medium">Fälligkeit</th>
                <th className="pb-2 font-medium text-right">Betrag</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium text-right">OP-Nr</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {ops.map((op: WKZOP) => (
                <tr key={op.id} className="hover:bg-gray-50">
                  <td className="py-1.5">
                    <Link to={`../../wkz-ops/${op.id}`} className="text-blue-600 hover:underline">
                      {DATUM(op.periode_von)}–{DATUM(op.periode_bis)}
                    </Link>
                  </td>
                  <td className="py-1.5">{DATUM(op.faellig_am)}</td>
                  <td className="py-1.5 text-right tabular-nums">{EUR(op.erwarteter_betrag)}</td>
                  <td className="py-1.5">
                    <Badge value={op.status} label={OP_STATUS_TEXT[op.status] ?? op.status} />
                  </td>
                  <td className="py-1.5 text-right font-mono text-xs">{op.op_nummer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showBeenden && (
        <BeendenModal vorlageId={id!} onClose={() => setShowBeenden(false)} />
      )}
    </div>
  )
}
