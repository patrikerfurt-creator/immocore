import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { buchhaltungApi } from '../../api/buchhaltung'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { useObjektStore } from '../../stores/objekt'

type WizardStep = 'auswahl' | 'simulation' | 'freigabe'

const STATUS_FARBE: Record<string, 'green' | 'yellow' | 'red' | 'gray' | 'blue'> = {
  simulation: 'yellow',
  ausstehend: 'blue',
  freigegeben: 'blue',
  ausgefuehrt: 'green',
  fehler: 'red',
}

export function Sollstellungen() {
  const objektId = useObjektStore(s => s.selectedId)
  const [showWizard, setShowWizard] = useState(false)
  const [step, setStep] = useState<WizardStep>('auswahl')
  const [periodeVon, setPeriodeVon] = useState('')
  const [periodeBis, setPeriodeBis] = useState('')
  const [simErgebnis, setSimErgebnis] = useState<Record<string, unknown> | null>(null)
  const [aktLaufId, setAktLaufId] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data: laeufe, isLoading } = useQuery({
    queryKey: ['sollstellungslaeufe', objektId],
    queryFn: () => buchhaltungApi.sollstellungslaeufe(objektId ?? undefined),
    enabled: !!objektId,
  })

  const simMut = useMutation({
    mutationFn: (data: { objekt: string; periode_von: string; periode_bis: string }) =>
      buchhaltungApi.sollstellungSimulieren(data),
    onSuccess: (data) => {
      setSimErgebnis(data)
      setStep('simulation')
    },
  })

  const anlegenMut = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      buchhaltungApi.sollstellungLaufAnlegen(data as never),
    onSuccess: (lauf) => {
      setAktLaufId(lauf.id)
      setStep('freigabe')
      qc.invalidateQueries({ queryKey: ['sollstellungslaeufe'] })
    },
  })

  const ausfuehrenMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.sollstellungAusfuehren(id),
    onSuccess: () => {
      setShowWizard(false)
      setStep('auswahl')
      setSimErgebnis(null)
      qc.invalidateQueries({ queryKey: ['sollstellungslaeufe'] })
    },
  })

  function handleSimulieren() {
    if (!objektId || !periodeVon || !periodeBis) return
    simMut.mutate({ objekt: objektId, periode_von: periodeVon, periode_bis: periodeBis })
  }

  function handleLaufAnlegen() {
    if (!objektId || !simErgebnis) return
    anlegenMut.mutate({
      objekt: objektId,
      periode_von: periodeVon,
      periode_bis: periodeBis,
      trigger: 'manuell',
      status: 'simulation',
    })
  }

  function handleAusfuehren() {
    if (!aktLaufId) return
    ausfuehrenMut.mutate(aktLaufId)
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
        <h1 className="text-2xl font-bold text-gray-900">Sollstellungen</h1>
        <Button onClick={() => { setShowWizard(true); setStep('auswahl') }}>
          + Neuer Lauf
        </Button>
      </div>

      {showWizard && (
        <div className="mb-8 border rounded-lg p-5 bg-white shadow-sm">
          <div className="flex gap-3 mb-5 text-sm font-medium">
            {(['auswahl', 'simulation', 'freigabe'] as WizardStep[]).map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                {i > 0 && <span className="text-gray-300">→</span>}
                <span className={step === s ? 'text-blue-600' : 'text-gray-400'}>
                  {i + 1}. {s === 'auswahl' ? 'Auswahl' : s === 'simulation' ? 'Simulation' : 'Freigabe'}
                </span>
              </div>
            ))}
          </div>

          {step === 'auswahl' && (
            <div className="space-y-4">
              <h2 className="font-semibold text-gray-800">Zeitraum wählen</h2>
              <div className="grid grid-cols-2 gap-4 max-w-sm">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Von (Monatsbeginn)</label>
                  <input
                    type="date"
                    value={periodeVon}
                    onChange={e => setPeriodeVon(e.target.value)}
                    className="border rounded px-3 py-2 text-sm w-full"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Bis (Monatsende)</label>
                  <input
                    type="date"
                    value={periodeBis}
                    onChange={e => setPeriodeBis(e.target.value)}
                    className="border rounded px-3 py-2 text-sm w-full"
                  />
                </div>
              </div>
              <div className="flex gap-3">
                <Button
                  onClick={handleSimulieren}
                  disabled={!periodeVon || !periodeBis || simMut.isPending}
                >
                  {simMut.isPending ? 'Simuliere…' : 'Vorschau erstellen'}
                </Button>
                <Button variant="outline" onClick={() => setShowWizard(false)}>
                  Abbrechen
                </Button>
              </div>
              {simMut.isError && (
                <p className="text-red-600 text-sm">Fehler bei der Simulation.</p>
              )}
            </div>
          )}

          {step === 'simulation' && simErgebnis && (
            <div className="space-y-4">
              <h2 className="font-semibold text-gray-800">Simulationsergebnis</h2>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="bg-gray-50 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-gray-800">
                    {(simErgebnis as never as { anzahl_positionen: number }).anzahl_positionen}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Buchungen</div>
                </div>
                <div className="bg-gray-50 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-gray-800">
                    {Number((simErgebnis as never as { gesamt_summe: number }).gesamt_summe).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Gesamtsumme</div>
                </div>
                <div className="bg-gray-50 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-red-600">
                    {(simErgebnis as never as { fehler: unknown[] }).fehler?.length ?? 0}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Fehler</div>
                </div>
              </div>

              <div className="max-h-60 overflow-y-auto border rounded text-sm">
                <table className="w-full">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="text-left px-3 py-2 text-gray-600">Eigentümer</th>
                      <th className="text-left px-3 py-2 text-gray-600">Einheit</th>
                      <th className="text-left px-3 py-2 text-gray-600">Periode</th>
                      <th className="text-left px-3 py-2 text-gray-600">BA</th>
                      <th className="text-right px-3 py-2 text-gray-600">Betrag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {((simErgebnis as never as { positionen: { person: string; einheit: string; monat: number; jahr: number; gesamt: number; positionen: { ba: string; betrag: number }[] }[] }).positionen ?? []).flatMap((p, i) =>
                      p.positionen.map((teil, j) => (
                        <tr key={`${i}-${j}`} className="border-t">
                          <td className="px-3 py-1.5">{p.person}</td>
                          <td className="px-3 py-1.5">{p.einheit}</td>
                          <td className="px-3 py-1.5 text-gray-500">
                            {String(p.monat).padStart(2, '0')}/{p.jahr}
                          </td>
                          <td className="px-3 py-1.5">
                            <Badge color="blue">{teil.ba}</Badge>
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            {Number(teil.betrag).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div className="flex gap-3">
                <Button onClick={handleLaufAnlegen} disabled={anlegenMut.isPending}>
                  {anlegenMut.isPending ? 'Erstelle Lauf…' : 'Lauf anlegen'}
                </Button>
                <Button variant="outline" onClick={() => setStep('auswahl')}>
                  Zurück
                </Button>
              </div>
            </div>
          )}

          {step === 'freigabe' && (
            <div className="space-y-4">
              <h2 className="font-semibold text-gray-800">Lauf ausführen</h2>
              <p className="text-sm text-gray-600">
                Der Sollstellungslauf ist angelegt. Jetzt ausführen?
              </p>
              <div className="flex gap-3">
                <Button
                  onClick={handleAusfuehren}
                  disabled={ausfuehrenMut.isPending}
                >
                  {ausfuehrenMut.isPending ? 'Führe aus…' : 'Jetzt ausführen'}
                </Button>
                <Button variant="outline" onClick={() => setShowWizard(false)}>
                  Später ausführen
                </Button>
              </div>
              {ausfuehrenMut.isError && (
                <p className="text-red-600 text-sm">Fehler bei der Ausführung.</p>
              )}
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
                <th className="text-left px-4 py-3 text-gray-600">Zeitraum</th>
                <th className="text-left px-4 py-3 text-gray-600">Trigger</th>
                <th className="text-right px-4 py-3 text-gray-600">Buchungen</th>
                <th className="text-right px-4 py-3 text-gray-600">Summe</th>
                <th className="text-left px-4 py-3 text-gray-600">Status</th>
                <th className="text-left px-4 py-3 text-gray-600">Erstellt</th>
              </tr>
            </thead>
            <tbody>
              {(laeufe ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-400">
                    Keine Läufe vorhanden
                  </td>
                </tr>
              ) : (laeufe ?? []).map(lauf => (
                <tr key={lauf.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3">
                    {new Date(lauf.periode_von).toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' })}
                    {' – '}
                    {new Date(lauf.periode_bis).toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' })}
                  </td>
                  <td className="px-4 py-3 capitalize">{lauf.trigger}</td>
                  <td className="px-4 py-3 text-right">{lauf.anzahl_buchungen}</td>
                  <td className="px-4 py-3 text-right">
                    {Number(lauf.gesamt_summe).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                  </td>
                  <td className="px-4 py-3">
                    <Badge color={STATUS_FARBE[lauf.status] ?? 'gray'}>{lauf.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(lauf.erstellt_am).toLocaleDateString('de-DE')}
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
