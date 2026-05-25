import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import { wirtschaftsjahreApi } from '../../api/wirtschaftsjahre'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { useObjektStore } from '../../stores/objekt'
import type { HausgeldSollstellungslauf, HausgeldSimulationVorschau } from '../../types'

type WizardStep = 'auswahl' | 'simulation'

const STATUS_LABEL: Record<string, string> = {
  vorschau:    'Vorschau',
  freigegeben: 'Freigegeben',
  commited:    'Commited',
  storniert:   'Storniert',
}

export function Sollstellungen() {
  const objektId = useObjektStore(s => s.selectedId)
  const [showWizard, setShowWizard] = useState(false)
  const [step, setStep] = useState<WizardStep>('auswahl')
  const [periode, setPeriode] = useState('')  // YYYY-MM
  const [wirtschaftsjahrId, setWirtschaftsjahrId] = useState('')
  const [vorschau, setVorschau] = useState<HausgeldSimulationVorschau | null>(null)

  // Auto-select the WJ that covers the given period (12-month window from beginn_monat)
  function wjFuerPeriode(periodeStr: string) {
    if (!periodeStr || !wirtschaftsjahre?.length) return undefined
    const [py, pm] = periodeStr.split('-').map(Number)
    const pval = py * 12 + pm
    return wirtschaftsjahre.find(wj => {
      const start = wj.jahr * 12 + wj.beginn_monat
      return pval >= start && pval <= start + 11
    })
  }

  function handlePeriodeChange(val: string) {
    setPeriode(val)
    if (val) {
      const match = wjFuerPeriode(val)
      if (match) setWirtschaftsjahrId(match.id)
      else setWirtschaftsjahrId('')
    }
  }
  const [expandedLauf, setExpandedLauf] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data: laeufe, isLoading } = useQuery({
    queryKey: ['hg-laeufe', objektId],
    queryFn: () => buchhaltungApi.hausgeldLaeufe(objektId ?? undefined),
    enabled: !!objektId,
  })

  const { data: wirtschaftsjahre } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => wirtschaftsjahreApi.list({ objekt: objektId ?? undefined }),
    enabled: !!objektId,
  })

  const simMut = useMutation({
    mutationFn: (data: { objekt_id: string; periode: string; wirtschaftsjahr_id?: string }) =>
      buchhaltungApi.simulierenHausgeld(data),
    onSuccess: (data) => {
      setVorschau(data)
      setStep('simulation')
      setFehler(null)
    },
    onError: (e: Error) => setFehler(e.message),
  })

  const erstellenMut = useMutation({
    mutationFn: (data: { objekt_id: string; periode: string; wirtschaftsjahr_id?: string }) =>
      buchhaltungApi.erstellenHausgeld(data),
    onSuccess: () => {
      setShowWizard(false)
      setStep('auswahl')
      setVorschau(null)
      qc.invalidateQueries({ queryKey: ['hg-laeufe'] })
    },
    onError: (e: Error) => setFehler(e.message),
  })

  const freigebenMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.freigebenHausgeld(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hg-laeufe'] }),
    onError: (e: Error) => setFehler(e.message),
  })

  const commitenMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.commitenHausgeld(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hg-laeufe'] })
      qc.invalidateQueries({ queryKey: ['hg-sollstellungen'] })
    },
    onError: (e: Error) => setFehler(e.message),
  })

  const stornierenMut = useMutation({
    mutationFn: ({ id, grund }: { id: string; grund: string }) =>
      buchhaltungApi.stornierenHausgeld(id, grund),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hg-laeufe'] }),
    onError: (e: Error) => setFehler(e.message),
  })

  function handleSimulieren() {
    if (!objektId || !periode) return
    simMut.mutate({
      objekt_id: objektId,
      periode,
      ...(wirtschaftsjahrId ? { wirtschaftsjahr_id: wirtschaftsjahrId } : {}),
    })
  }

  function handleErstellen() {
    if (!objektId || !periode) return
    erstellenMut.mutate({
      objekt_id: objektId,
      periode,
      ...(wirtschaftsjahrId ? { wirtschaftsjahr_id: wirtschaftsjahrId } : {}),
    })
  }

  function handleStornieren(lauf: HausgeldSollstellungslauf) {
    const grund = window.prompt(`Storno-Grund für Lauf ${lauf.periode}?`)
    if (grund === null) return
    stornierenMut.mutate({ id: lauf.id, grund })
  }

  if (!objektId) {
    return (
      <div className="p-6 text-gray-500">
        Bitte zuerst ein Objekt in der Seitenleiste auswählen.
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Sollstellungen (Hausgeld)</h1>
        <Button onClick={() => { setShowWizard(true); setStep('auswahl'); setVorschau(null); setFehler(null); setWirtschaftsjahrId('') }}>
          + Neuer Lauf
        </Button>
      </div>

      {fehler && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
          {fehler}
          <button className="ml-3 text-red-500 underline text-xs" onClick={() => setFehler(null)}>Schließen</button>
        </div>
      )}

      {showWizard && (
        <div className="mb-8 border rounded-lg p-5 bg-white shadow-sm">
          <div className="flex gap-3 mb-5 text-sm font-medium">
            {(['auswahl', 'simulation'] as WizardStep[]).map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                {i > 0 && <span className="text-gray-300">→</span>}
                <span className={step === s ? 'text-blue-600' : 'text-gray-400'}>
                  {i + 1}. {s === 'auswahl' ? 'Vorschau' : 'Bestätigen'}
                </span>
              </div>
            ))}
          </div>

          {step === 'auswahl' && (
            <div className="space-y-4">
              <h2 className="font-semibold text-gray-800">Monat wählen</h2>
              <div className="grid grid-cols-2 gap-4 max-w-lg">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Wirtschaftsjahr</label>
                  <select
                    value={wirtschaftsjahrId}
                    onChange={e => setWirtschaftsjahrId(e.target.value)}
                    className="border rounded px-3 py-2 text-sm w-full"
                  >
                    <option value="">— bitte wählen —</option>
                    {(wirtschaftsjahre ?? []).map(wj => (
                      <option key={wj.id} value={wj.id}>
                        {wj.jahr} {wj.status === 'abgeschlossen' ? '(abgeschlossen)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Periode (Monat/Jahr)</label>
                  <input
                    type="month"
                    value={periode}
                    onChange={e => handlePeriodeChange(e.target.value)}
                    className="border rounded px-3 py-2 text-sm w-full"
                  />
                </div>
              </div>
              {periode && !wjFuerPeriode(periode) && (
                <div className="text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-xs">
                  Kein Wirtschaftsjahr deckt {new Date(periode + '-01T12:00:00').toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' })} ab.
                  {wirtschaftsjahrId ? '' : ' Bitte manuell ein WJ wählen oder zuerst ein Folgejahr anlegen.'}
                </div>
              )}
              <div className="flex gap-3">
                <Button
                  onClick={handleSimulieren}
                  disabled={!periode || simMut.isPending}
                >
                  {simMut.isPending ? 'Simuliere…' : 'Vorschau erstellen'}
                </Button>
                <Button variant="secondary" onClick={() => setShowWizard(false)}>
                  Abbrechen
                </Button>
              </div>
              {simMut.isError && (
                <p className="text-red-600 text-sm">Fehler bei der Simulation.</p>
              )}
            </div>
          )}

          {step === 'simulation' && vorschau && (
            <div className="space-y-4">
              <h2 className="font-semibold text-gray-800">Vorschau — {vorschau.periode}</h2>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="bg-gray-50 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-gray-800">{vorschau.anzahl_evs}</div>
                  <div className="text-xs text-gray-500 mt-1">Eigentümer</div>
                </div>
                <div className="bg-gray-50 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-gray-800">
                    {Number(vorschau.gesamtsumme).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Gesamtsumme</div>
                </div>
                <div className="bg-gray-50 rounded p-3 text-center">
                  <div className={`text-2xl font-bold ${vorschau.warnungen.length > 0 ? 'text-amber-600' : 'text-gray-400'}`}>
                    {vorschau.warnungen.length}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Warnungen</div>
                </div>
              </div>

              {vorschau.warnungen.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-800 space-y-1">
                  {vorschau.warnungen.map((w, i) => <div key={i}>⚠ {w}</div>)}
                </div>
              )}

              <div className="max-h-64 overflow-y-auto border rounded text-sm">
                <table className="w-full">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="text-left px-3 py-2 text-gray-600">Eigentümer</th>
                      <th className="text-left px-3 py-2 text-gray-600">Einheit</th>
                      <th className="text-left px-3 py-2 text-gray-600">Splits (BA: Betrag)</th>
                      <th className="text-right px-3 py-2 text-gray-600">Summe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vorschau.positionen.map((p) => (
                      <tr key={p.eigentumsverhaeltnis_id} className="border-t">
                        <td className="px-3 py-1.5">{p.eigentuemer_name}</td>
                        <td className="px-3 py-1.5">{p.einheit_nr}</td>
                        <td className="px-3 py-1.5">
                          <div className="flex flex-wrap gap-1">
                            {p.splits.map(s => (
                              <span key={s.ba_code} className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 rounded px-1.5 py-0.5">
                                {s.ba_code}: {Number(s.betrag).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="px-3 py-1.5 text-right font-medium">
                          {Number(p.summe).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex gap-3">
                <Button onClick={handleErstellen} disabled={erstellenMut.isPending}>
                  {erstellenMut.isPending ? 'Erstelle Lauf…' : 'Lauf anlegen (Status: Vorschau)'}
                </Button>
                <Button variant="secondary" onClick={() => setStep('auswahl')}>
                  Zurück
                </Button>
              </div>
              <p className="text-xs text-gray-500">
                Nach dem Anlegen kann ein zweiter Benutzer den Lauf freigeben, danach kann er commited werden.
              </p>
            </div>
          )}
        </div>
      )}

      {isLoading ? (
        <div className="text-gray-500 text-sm">Lade Läufe…</div>
      ) : (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-600">WJ</th>
                <th className="text-left px-4 py-3 text-gray-600">Periode</th>
                <th className="text-left px-4 py-3 text-gray-600">Typ</th>
                <th className="text-right px-4 py-3 text-gray-600">Anzahl</th>
                <th className="text-right px-4 py-3 text-gray-600">Summe</th>
                <th className="text-left px-4 py-3 text-gray-600">Status</th>
                <th className="text-left px-4 py-3 text-gray-600">Erstellt</th>
                <th className="text-left px-4 py-3 text-gray-600">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {(laeufe ?? []).length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-gray-400">
                    Keine Läufe vorhanden
                  </td>
                </tr>
              ) : (laeufe ?? []).map(lauf => (
                <>
                  <tr
                    key={lauf.id}
                    className="border-t hover:bg-gray-50 cursor-pointer"
                    onClick={() => setExpandedLauf(expandedLauf === lauf.id ? null : lauf.id)}
                  >
                    <td className="px-4 py-3 text-gray-500 font-mono text-xs">
                      {lauf.wirtschaftsjahr_jahr ?? '—'}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {lauf.periode ? new Date(lauf.periode + 'T12:00:00').toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' }) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{lauf.typ === 'hausgeld_monat' ? 'Hausgeld monatlich' : lauf.typ}</td>
                    <td className="px-4 py-3 text-right">{lauf.anzahl_sollstellungen}</td>
                    <td className="px-4 py-3 text-right">
                      {Number(lauf.summe).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                    </td>
                    <td className="px-4 py-3">
                      <Badge value={lauf.status} label={STATUS_LABEL[lauf.status] ?? lauf.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(lauf.erstellt_am).toLocaleDateString('de-DE')}
                      {lauf.erstellt_von_name && <span className="text-xs ml-1">({lauf.erstellt_von_name})</span>}
                    </td>
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      <div className="flex gap-2">
                        {lauf.status === 'vorschau' && (
                          <Button
                            size="sm"
                            onClick={() => freigebenMut.mutate(lauf.id)}
                            disabled={freigebenMut.isPending}
                          >
                            Freigeben
                          </Button>
                        )}
                        {lauf.status === 'freigegeben' && (
                          <Button
                            size="sm"
                            onClick={() => commitenMut.mutate(lauf.id)}
                            disabled={commitenMut.isPending}
                          >
                            Commiten
                          </Button>
                        )}
                        {(lauf.status === 'vorschau' || lauf.status === 'commited') && (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => handleStornieren(lauf)}
                            disabled={stornierenMut.isPending}
                          >
                            Stornieren
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedLauf === lauf.id && (
                    <tr key={`${lauf.id}-detail`} className="bg-blue-50">
                      <td colSpan={8} className="px-6 py-3 text-xs text-gray-700 space-y-1">
                        {lauf.freigabe_user_name && (
                          <div>Freigegeben von: <strong>{lauf.freigabe_user_name}</strong>
                            {lauf.freigegeben_am && ` am ${new Date(lauf.freigegeben_am).toLocaleString('de-DE')}`}
                          </div>
                        )}
                        {lauf.commited_am && (
                          <div>Commited am: <strong>{new Date(lauf.commited_am).toLocaleString('de-DE')}</strong></div>
                        )}
                        {lauf.storniert_am && (
                          <div>Storniert am: <strong>{new Date(lauf.storniert_am).toLocaleString('de-DE')}</strong>
                            {lauf.storniert_grund && ` — ${lauf.storniert_grund}`}
                          </div>
                        )}
                        <div className="pt-1 text-gray-500">
                          Lauf-ID: <span className="font-mono">{lauf.id}</span>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

    </div>
  )
}
