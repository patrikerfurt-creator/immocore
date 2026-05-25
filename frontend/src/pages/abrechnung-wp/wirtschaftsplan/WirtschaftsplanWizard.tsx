import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi, WpKonto } from '../../../api/wirtschaftsplan'
import { objekteApi } from '../../../api/objekte'

type Step = 1 | 2 | 3 | 4

interface Step1Data {
  wirtschaftsjahr_id: string
  wirkung_ab: string
}

function fmt(v: string | number) {
  return Number(v).toLocaleString('de-DE', { minimumFractionDigits: 2 })
}

function StatusAmpel({ konto }: { konto: WpKonto }) {
  if (!konto.hat_vs) return <span title="Kein VS hinterlegt" className="text-red-500">🔴</span>
  if (konto.verteilung_freigegeben_trotz_diff) return <span title="Freigegeben trotz Differenz" className="text-yellow-500">🟡</span>
  if (konto.verteilung_validiert) return <span title="Verteilung ok" className="text-green-500">🟢</span>
  if (konto.betrag === '0.00' || konto.betrag === '0') return <span title="Noch kein Betrag" className="text-gray-300">⚪</span>
  return <span title="Wird berechnet..." className="text-yellow-400">🟡</span>
}

// ─── Schritt 1: Wirtschaftsjahr auswählen ───────────────────────────────────
function Schritt1({ objektId, onWeiter }: { objektId: string; onWeiter: (d: Step1Data) => void }) {
  const [wjId, setWjId] = useState('')
  const [wirkungAb, setWirkungAb] = useState('')

  const { data: objekt } = useQuery({
    queryKey: ['objekt', objektId],
    queryFn: () => objekteApi.get(objektId),
    enabled: !!objektId,
  })

  const { data: wirtschaftsjahre = [] } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => objekteApi.wirtschaftsjahre(objektId),
    enabled: !!objektId,
  })

  useEffect(() => {
    if (wirtschaftsjahre.length > 0 && !wjId) {
      const aktiv = wirtschaftsjahre.find((w: any) => w.status === 'offen')
      if (aktiv) {
        setWjId(aktiv.id)
        setWirkungAb(`${aktiv.jahr}-01-01`)
      }
    }
  }, [wirtschaftsjahre])

  const handleWeiter = () => {
    if (!wjId || !wirkungAb) return
    onWeiter({ wirtschaftsjahr_id: wjId, wirkung_ab: wirkungAb })
  }

  const selectedWj = wirtschaftsjahre.find((w: any) => w.id === wjId)
  const istRueckwirkend = wirkungAb && new Date(wirkungAb) < new Date()

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Objekt</label>
        <p className="text-sm text-gray-900">{objekt?.bezeichnung ?? '—'}</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Wirtschaftsjahr</label>
        <select
          value={wjId}
          onChange={e => {
            setWjId(e.target.value)
            const wj = wirtschaftsjahre.find((w: any) => w.id === e.target.value)
            if (wj) setWirkungAb(`${wj.jahr}-01-01`)
          }}
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
        >
          <option value="">— bitte wählen —</option>
          {wirtschaftsjahre.map((wj: any) => (
            <option key={wj.id} value={wj.id}>
              WJ {wj.jahr} ({wj.status})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Wirkung ab</label>
        <input
          type="date"
          value={wirkungAb}
          onChange={e => setWirkungAb(e.target.value)}
          min={selectedWj ? `${selectedWj.jahr}-01-01` : undefined}
          max={selectedWj ? `${selectedWj.jahr}-12-31` : undefined}
          className="border border-gray-300 rounded px-3 py-2 text-sm"
        />
        {istRueckwirkend && (
          <p className="text-xs text-amber-600 mt-1">
            ⚠ Rückwirkender Beschluss — Differenz-Workflow wird aktiviert (noch nicht vollständig implementiert).
          </p>
        )}
      </div>
      <div className="flex justify-end">
        <button
          disabled={!wjId || !wirkungAb}
          onClick={handleWeiter}
          className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50"
        >
          Weiter →
        </button>
      </div>
    </div>
  )
}

// ─── Schritt 2: Konten und Beträge eingeben ─────────────────────────────────
function Schritt2({
  wpId,
  onWeiter,
  onZurueck,
}: { wpId: string; onWeiter: () => void; onZurueck: () => void }) {
  const qc = useQueryClient()
  const [betraege, setBetraege] = useState<Record<string, string>>({})
  const debounceRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const { data: konten = [], isLoading } = useQuery({
    queryKey: ['wp-konten', wpId],
    queryFn: () => wirtschaftsplanApi.konten(wpId),
  })

  // Initialbeträge aus vorhandenen Positionen laden
  useEffect(() => {
    const init: Record<string, string> = {}
    konten.forEach(k => { init[k.id] = k.betrag === '0.00' ? '' : k.betrag })
    setBetraege(init)
  }, [konten])

  const upsertMut = useMutation({
    mutationFn: ({ kontoId, betrag }: { kontoId: string; betrag: string }) =>
      wirtschaftsplanApi.positionUpsert(wpId, { konto_id: kontoId, betrag }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wp-konten', wpId] }),
  })

  const deleteMut = useMutation({
    mutationFn: (kontoId: string) => wirtschaftsplanApi.positionLoeschen(wpId, kontoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wp-konten', wpId] }),
  })

  const handleBetragChange = (kontoId: string, val: string) => {
    setBetraege(prev => ({ ...prev, [kontoId]: val }))
    clearTimeout(debounceRef.current[kontoId])
    debounceRef.current[kontoId] = setTimeout(() => {
      const num = parseFloat(val.replace(',', '.'))
      if (!isNaN(num) && num >= 0) {
        upsertMut.mutate({ kontoId, betrag: num.toFixed(2) })
      } else if (val === '' || val === '0') {
        deleteMut.mutate(kontoId)
      }
    }, 600)
  }

  const gesamtsumme = konten.reduce((s, k) => s + parseFloat(k.betrag || '0'), 0)
  const hausgeld = konten.filter(k => k.abrechnungsart === '900' || (!k.abrechnungsart && k.kontonummer >= '50000' && k.kontonummer <= '55999'))
    .reduce((s, k) => s + parseFloat(k.betrag || '0'), 0)

  return (
    <div className="space-y-4">
      {isLoading ? (
        <p className="text-sm text-gray-400">Lade Konten...</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Konto</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">VS</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-600">Jahresbetrag €</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {konten.map(k => (
                  <tr key={k.id} className={k.kontoart === 'summierung' ? 'bg-blue-50' : ''}>
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs text-gray-500 mr-2">{k.kontonummer}</span>
                      {k.kontoname}
                      {k.kontoart === 'summierung' && (
                        <span className="ml-2 text-xs text-blue-500">(Summierung)</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500">
                      {k.vs_code ?? <span className="text-red-500">kein VS</span>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={betraege[k.id] ?? ''}
                        onChange={e => handleBetragChange(k.id, e.target.value)}
                        placeholder="0,00"
                        className="w-32 text-right border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:border-primary-500"
                      />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <StatusAmpel konto={k} />
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t-2 border-gray-300 bg-gray-50">
                <tr>
                  <td colSpan={2} className="px-3 py-2 text-sm font-medium">
                    Summe Hausgeld
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-medium">{fmt(hausgeld)} €</td>
                  <td />
                </tr>
                <tr>
                  <td colSpan={2} className="px-3 py-2 text-sm font-bold">
                    GESAMTSUMME
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-bold">{fmt(gesamtsumme)} €</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="flex justify-between pt-2">
            <button
              onClick={onZurueck}
              className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50"
            >
              ← Zurück
            </button>
            <button
              onClick={onWeiter}
              className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700"
            >
              Weiter →
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Schritt 3: Verteilungs-Kontrolle ───────────────────────────────────────
function Schritt3({
  wpId,
  onWeiter,
  onZurueck,
}: { wpId: string; onWeiter: () => void; onZurueck: () => void }) {
  const qc = useQueryClient()

  // WP-Detail liefert positionen mit summe_anteile und differenz
  const { data: wp, isLoading } = useQuery({
    queryKey: ['wp-detail', wpId],
    queryFn: () => wirtschaftsplanApi.get(wpId),
  })

  const freigebeMut = useMutation({
    mutationFn: (kontoId: string) => wirtschaftsplanApi.freigabeTrotzDiff(wpId, kontoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wp-detail', wpId] })
      qc.invalidateQueries({ queryKey: ['wp-konten', wpId] })
    },
  })

  const positionen = (wp?.positionen ?? []).filter(p => parseFloat(p.betrag) > 0)
  const alleFreigegeben = positionen.every(
    p => p.verteilung_validiert || p.verteilung_freigegeben_trotz_diff
  )

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Differenzen entstehen durch kaufmännische Rundung. Bis 0,10 € automatisch toleriert.
        Größere Differenzen können manuell freigegeben werden.
      </p>
      {isLoading ? (
        <p className="text-sm text-gray-400">Lade...</p>
      ) : (
        <>
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Konto</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">VS</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Betrag €</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Summe Anteile €</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Differenz €</th>
                <th className="px-3 py-2 text-center font-medium text-gray-600">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {positionen.map(pos => {
                const diff = pos.differenz
                const absDiff = Math.abs(diff)
                const diffColor = absDiff <= 0.10 ? 'text-green-600' : absDiff <= 1.00 ? 'text-amber-600' : 'text-red-600'
                return (
                  <tr key={pos.id}>
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs text-gray-500 mr-2">{pos.konto_nr}</span>
                      {pos.konto_name}
                    </td>
                    <td className="px-3 py-2 text-xs">{pos.vs_code}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt(pos.betrag)}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt(pos.summe_anteile)}</td>
                    <td className={`px-3 py-2 text-right font-mono ${diffColor}`}>
                      {diff > 0 ? '+' : ''}{fmt(diff)}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {pos.verteilung_validiert ? (
                        <span className="text-green-500">🟢</span>
                      ) : pos.verteilung_freigegeben_trotz_diff ? (
                        <span className="text-yellow-500" title="Manuell freigegeben">🟡</span>
                      ) : (
                        <>
                          <span className={absDiff <= 1.00 ? 'text-yellow-500' : 'text-red-500'}>
                            {absDiff <= 1.00 ? '🟡' : '🔴'}
                          </span>
                          <button
                            onClick={() => freigebeMut.mutate(pos.konto)}
                            disabled={freigebeMut.isPending}
                            className="ml-2 text-xs text-amber-600 hover:underline"
                          >
                            Freigeben
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {positionen.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-4">
              Noch keine Positionen mit Betrag &gt; 0.
            </p>
          )}

          <div className="flex justify-between pt-2">
            <button
              onClick={onZurueck}
              className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50"
            >
              ← Zurück
            </button>
            <button
              onClick={onWeiter}
              disabled={!alleFreigegeben || positionen.length === 0}
              className="px-4 py-2 bg-primary-600 text-white text-sm rounded hover:bg-primary-700 disabled:opacity-50"
              title={!alleFreigegeben ? 'Alle Positionen müssen validiert oder freigegeben sein' : ''}
            >
              Weiter →
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Schritt 4: Hausgeld-Vorschau ───────────────────────────────────────────
function Schritt4({
  wpId,
  onWeiter,
  onZurueck,
}: { wpId: string; onWeiter: () => void; onZurueck: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['wp-vorschau', wpId],
    queryFn: () => wirtschaftsplanApi.vorschauHausgeld(wpId),
  })

  const vorschau = data?.vorschau ?? []
  const baCodes = vorschau.length > 0 ? Object.keys(vorschau[0].ba_betraege) : []

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Vorschau der monatlichen Hausgeld-Sollanteile je Eigentümer nach Beschluss.
      </p>
      {isLoading ? (
        <p className="text-sm text-gray-400">Berechne Vorschau...</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Einheit</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Eigentümer</th>
                  {baCodes.map(ba => (
                    <th key={ba} className="px-3 py-2 text-right font-medium text-gray-600">.{ba} €/Mon</th>
                  ))}
                  <th className="px-3 py-2 text-right font-medium text-gray-600">Summe €/Mon</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-600">Δ aktuell</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {vorschau.map(z => (
                  <tr key={z.ev_id}>
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs">{z.einheit_nr}</span>
                      {z.lage && <span className="text-gray-400 text-xs ml-1">— {z.lage}</span>}
                    </td>
                    <td className="px-3 py-2">{z.person_name}</td>
                    {baCodes.map(ba => (
                      <td key={ba} className="px-3 py-2 text-right font-mono">
                        {fmt(z.ba_betraege[ba] ?? 0)}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-right font-mono font-medium">{fmt(z.summe)}</td>
                    <td className={`px-3 py-2 text-right font-mono text-xs ${z.delta > 0 ? 'text-red-600' : z.delta < 0 ? 'text-green-600' : 'text-gray-400'}`}>
                      {z.delta > 0 ? '+' : ''}{fmt(z.delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-between pt-2">
            <button
              onClick={onZurueck}
              className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50"
            >
              ← Zurück
            </button>
            <button
              onClick={onWeiter}
              className="px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700"
            >
              Entwurf anzeigen →
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Haupt-Wizard ────────────────────────────────────────────────────────────
const STEP_LABELS = ['Wirtschaftsjahr', 'Konten', 'Verteilung', 'Vorschau']

export function WirtschaftsplanWizard() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const objektId = searchParams.get('objekt') ?? ''
  const existingWpId = searchParams.get('wp')
  const qc = useQueryClient()

  const [step, setStep] = useState<Step>(existingWpId ? 2 : 1)
  const [wpId, setWpId] = useState<string | null>(existingWpId)

  const erstellenMut = useMutation({
    mutationFn: (d: { wirtschaftsjahr_id: string; wirkung_ab: string }) =>
      wirtschaftsplanApi.create(d),
    onSuccess: (neu) => {
      setWpId(neu.id)
      setStep(2)
      qc.invalidateQueries({ queryKey: ['wirtschaftsplaene'] })
    },
  })

  const handleSchritt1 = (d: { wirtschaftsjahr_id: string; wirkung_ab: string }) => {
    erstellenMut.mutate(d)
  }

  const handleEntwurfFertig = () => {
    qc.invalidateQueries({ queryKey: ['wirtschaftsplaene'] })
    navigate(`/abrechnung-wp/wirtschaftsplan/${wpId}`)
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Wirtschaftsplan Wizard</h1>
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Abbrechen ✕
        </button>
      </div>

      {/* Schrittanzeige */}
      <div className="flex items-center gap-1">
        {STEP_LABELS.map((label, i) => (
          <div key={label} className="flex items-center">
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${
              step === i + 1
                ? 'bg-primary-600 text-white'
                : step > i + 1
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-400'
            }`}>
              {step > i + 1 ? '✓ ' : `${i + 1}. `}{label}
            </div>
            {i < STEP_LABELS.length - 1 && <span className="text-gray-300 mx-0.5">›</span>}
          </div>
        ))}
      </div>

      {/* Schritt-Inhalt */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        {step === 1 && (
          <Schritt1 objektId={objektId} onWeiter={handleSchritt1} />
        )}
        {step === 2 && wpId && (
          <Schritt2
            wpId={wpId}
            onWeiter={() => setStep(3)}
            onZurueck={() => setStep(1)}
          />
        )}
        {step === 3 && wpId && (
          <Schritt3
            wpId={wpId}
            onWeiter={() => setStep(4)}
            onZurueck={() => setStep(2)}
          />
        )}
        {step === 4 && wpId && (
          <Schritt4
            wpId={wpId}
            onWeiter={handleEntwurfFertig}
            onZurueck={() => setStep(3)}
          />
        )}

        {erstellenMut.isPending && (
          <p className="text-sm text-gray-400 mt-2">Erstelle Wirtschaftsplan...</p>
        )}
        {erstellenMut.isError && (
          <p className="text-sm text-red-600 mt-2">
            Fehler: {(erstellenMut.error as any)?.response?.data?.detail ?? 'Unbekannter Fehler'}
          </p>
        )}
      </div>
    </div>
  )
}
