import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wkzApi } from '../../../api/wkz'
import { Badge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'

const EUR = (v: string | number | null) =>
  v !== null ? Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }) : '–'

const DATUM = (s: string | null) =>
  s ? new Date(s).toLocaleDateString('de-DE') : '–'

const STATUS_TEXT: Record<string, string> = {
  erzeugt: 'Erzeugt — wartet auf Bankabgang',
  bescheid_fehlt: 'Bescheid fehlt',
  bankabgang_erfolgt: 'Bankabgang verbucht',
  abweichend_geklaert: 'Abweichender Betrag, geklärt',
  verworfen: 'Verworfen',
}

// ---------------------------------------------------------------------------
// Verwerfen-Modal
// ---------------------------------------------------------------------------

function VerwerfenModal({
  opId,
  onClose,
}: {
  opId: string
  onClose: () => void
}) {
  const [grund, setGrund] = useState('')
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => wkzApi.opVerwerfen(opId, grund),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wkz-op', opId] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md space-y-4">
        <h2 className="text-lg font-semibold">OP verwerfen</h2>
        <p className="text-sm text-gray-600">
          Der zugehörige Kreditor-OP wird storniert. Diese Aktion kann nicht rückgängig gemacht werden.
        </p>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Grund *</label>
          <textarea
            value={grund}
            onChange={e => setGrund(e.target.value)}
            rows={3}
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
            disabled={!grund || mutation.isPending}
          >
            Verwerfen
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

export default function OPDetail() {
  const { id } = useParams<{ id: string }>()
  const [showVerwerfen, setShowVerwerfen] = useState(false)

  const { data: op, isLoading, error } = useQuery({
    queryKey: ['wkz-op', id],
    queryFn: () => wkzApi.opDetail(id!),
    enabled: !!id,
  })

  if (isLoading) return <p className="p-4 text-gray-400">Lade OP…</p>
  if (error || !op) return <p className="p-4 text-red-600">Fehler beim Laden.</p>

  const kannVerworfen = !['bankabgang_erfolgt', 'abweichend_geklaert', 'verworfen'].includes(op.status)

  return (
    <div className="p-4 max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to=".." className="text-gray-500 hover:text-gray-800 text-sm">
            ← Zurück
          </Link>
          <h1 className="text-xl font-semibold">WKZ-OP</h1>
          <Badge value={op.status} label={STATUS_TEXT[op.status] ?? op.status} />
        </div>
        {kannVerworfen && (
          <Button variant="secondary" onClick={() => setShowVerwerfen(true)}>
            Verwerfen
          </Button>
        )}
      </div>

      {/* Details */}
      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-gray-500">Vorlage</dt>
            <dd>
              <Link
                to={`../wkz-vorlagen/${op.vorlage}`}
                className="text-blue-600 hover:underline"
              >
                {op.vorlage_bezeichnung}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Kreditor</dt>
            <dd>{op.kreditor_name}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Periode</dt>
            <dd>
              {DATUM(op.periode_von)} – {DATUM(op.periode_bis)}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Fälligkeit</dt>
            <dd>{DATUM(op.faellig_am)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Erwarteter Betrag</dt>
            <dd className="font-medium">{EUR(op.erwarteter_betrag)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">OP-Nummer</dt>
            <dd className="font-mono">{op.op_nummer}</dd>
          </div>
          {op.abweichung_betrag && (
            <div>
              <dt className="text-gray-500">Abweichung</dt>
              <dd className="text-yellow-600">{EUR(op.abweichung_betrag)}</dd>
            </div>
          )}
          {op.klaerungs_grund && (
            <div className="col-span-2">
              <dt className="text-gray-500">Klärungsgrund</dt>
              <dd className="text-gray-700">{op.klaerungs_grund}</dd>
            </div>
          )}
          {op.bank_match_buchung_id && (
            <div>
              <dt className="text-gray-500">Buchung</dt>
              <dd>
                <Link
                  to={`/buchungen/${op.bank_match_buchung_id}`}
                  className="text-blue-600 hover:underline font-mono text-xs"
                >
                  {op.bank_match_buchung_id.slice(0, 8)}…
                </Link>
              </dd>
            </div>
          )}
        </dl>
      </div>

      {/* Splits (Buchungsvorschau) */}
      {op.splits && op.splits.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="font-medium text-gray-800 mb-3">Buchungsvorschau (Splits)</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="pb-2 font-medium">Soll</th>
                <th className="pb-2 font-medium">Konto</th>
                <th className="pb-2 font-medium text-right">Betrag</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {op.splits.map(s => (
                <tr key={s.id}>
                  <td className="py-1.5">{s.bezeichnung}</td>
                  <td className="py-1.5 font-mono text-xs">{s.kontonummer}</td>
                  <td className="py-1.5 text-right tabular-nums">{EUR(s.betrag)}</td>
                </tr>
              ))}
              <tr className="border-t border-gray-300">
                <td className="pt-2 font-medium" colSpan={2}>
                  Haben — Bank (18xxx)
                </td>
                <td className="pt-2 text-right font-medium tabular-nums">
                  {EUR(op.erwarteter_betrag)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Erzeugt am */}
      <p className="text-xs text-gray-400">
        Erzeugt am {DATUM(op.erzeugt_am)}
      </p>

      {showVerwerfen && (
        <VerwerfenModal opId={id!} onClose={() => setShowVerwerfen(false)} />
      )}
    </div>
  )
}
