import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { prozesseApi } from '../../api/prozesse'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Stepper } from '../../components/ui/Stepper'
import type { StepperStep } from '../../components/ui/Stepper'
import type { ProzessTyp, EWAbschlussErgebnis } from '../../types'

import { EW_Step01_EinheitStichtag } from './steps/EW_Step01_EinheitStichtag'
import { EW_Step02_Kaeufer } from './steps/EW_Step02_Kaeufer'
import { EW_Step03_HausgeldSollwerte } from './steps/EW_Step03_HausgeldSollwerte'
import { EW_Step04_Analyse } from './steps/EW_Step04_Analyse'
import { EW_Step05_Vorschau } from './steps/EW_Step05_Vorschau'

import { Step01_Objekttyp } from './steps/Step01_Objekttyp'
import { Step02_Stammdaten } from './steps/Step02_Stammdaten'
import { Step03_Eingaenge } from './steps/Step03_Eingaenge'
import { Step04a_Wirtschaftsjahr } from './steps/Step04a_Wirtschaftsjahr'
import { Step04_Einheiten } from './steps/Step04_Einheiten'
import { Step06_Bankkonten } from './steps/Step06_Bankkonten'
import { Step07_Kontenrahmen } from './steps/Step07_Kontenrahmen'
import { Step08_Vertraege } from './steps/Step08_Vertraege'
import { Step09_Freigabelimits } from './steps/Step09_Freigabelimits'
import { Step10_Review } from './steps/Step10_Review'

const PROZESS_TYPEN: { value: ProzessTyp; label: string }[] = [
  { value: 'objekt_anlegen',     label: 'Objekt anlegen' },
  { value: 'eigentuemerwechsel', label: 'Eigentümerwechsel' },
  { value: 'jahresabrechnung',   label: 'Jahresabrechnung' },
]

const STEP_LABELS: { nr: number; bezeichnung: string }[] = [
  { nr: 1,  bezeichnung: 'Objekttyp' },
  { nr: 2,  bezeichnung: 'Stammdaten' },
  { nr: 3,  bezeichnung: 'Eingänge' },
  { nr: 4,  bezeichnung: 'Wirtschaftsjahr' },
  { nr: 5,  bezeichnung: 'Einheiten' },
  { nr: 6,  bezeichnung: 'Bankkonten' },
  { nr: 7,  bezeichnung: 'Kontenrahmen' },
  { nr: 8,  bezeichnung: 'Verträge' },
  { nr: 9,  bezeichnung: 'Freigabelimits' },
  { nr: 10, bezeichnung: 'Review & Aktivierung' },
]

const EW_STEP_LABELS: { nr: number; bezeichnung: string }[] = [
  { nr: 1, bezeichnung: 'Einheit & Stichtag' },
  { nr: 2, bezeichnung: 'Käufer erfassen' },
  { nr: 3, bezeichnung: 'Hausgeld-Sollwerte' },
  { nr: 4, bezeichnung: 'Sollstellungs-Analyse' },
  { nr: 5, bezeichnung: 'Vorschau & Bestätigung' },
]

function buildStepperSchritte(
  labels: { nr: number; bezeichnung: string }[],
  currentNr: number,
  processCurrentStep: number
): StepperStep[] {
  return labels.map(({ nr, bezeichnung }) => {
    let status: StepperStep['status']
    if (nr < processCurrentStep) {
      status = 'abgeschlossen'
    } else if (nr === currentNr) {
      status = 'aktiv'
    } else {
      status = 'ausstehend'
    }
    return { nr, bezeichnung, status }
  })
}

function extractErrors(err: unknown): string[] {
  const response = (err as { response?: { data?: unknown } })?.response?.data
  if (!response) return ['Ein unbekannter Fehler ist aufgetreten.']
  if (typeof response === 'string') return [response]
  if (typeof response === 'object' && response !== null) {
    const detail = (response as Record<string, unknown>).detail
    if (typeof detail === 'string') return [detail]
    // Flatten field errors
    const msgs: string[] = []
    for (const [key, val] of Object.entries(response as Record<string, unknown>)) {
      if (Array.isArray(val)) {
        val.forEach(v => msgs.push(`${key}: ${v}`))
      } else if (typeof val === 'string') {
        msgs.push(`${key}: ${val}`)
      }
    }
    if (msgs.length > 0) return msgs
  }
  return ['Ein Fehler ist aufgetreten.']
}

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

export function ProzessWizard() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const typParam = searchParams.get('typ') as ProzessTyp | null

  const [neuerTyp, setNeuerTyp] = useState<ProzessTyp>(
    typParam && PROZESS_TYPEN.some(t => t.value === typParam) ? typParam : 'objekt_anlegen'
  )
  const [neuerObjektId, setNeuerObjektId] = useState('')
  const [activeProzessId, setActiveProzessId] = useState<string | null>(null)
  const [currentNr, setCurrentNr] = useState(1)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [stepErrors, setStepErrors] = useState<string[]>([])
  const [ewAbschlussErgebnis, setEwAbschlussErgebnis] = useState<EWAbschlussErgebnis | null>(null)

  // Sync neuerTyp when URL param changes
  useEffect(() => {
    if (typParam && PROZESS_TYPEN.some(t => t.value === typParam)) {
      setNeuerTyp(typParam)
    }
  }, [typParam])

  // ── Queries ──────────────────────────────────────────────────────────
  const { data: prozesse, isLoading: prozesseLoading } = useQuery({
    queryKey: ['prozesse'],
    queryFn: () => prozesseApi.list(),
  })

  const { data: objekte } = useQuery({
    queryKey: ['objekte'],
    queryFn: objekteApi.list,
  })

  const { data: aktiverProzess, refetch: refetchAktiverProzess } = useQuery({
    queryKey: ['prozess', activeProzessId],
    queryFn: () => prozesseApi.get(activeProzessId!),
    enabled: !!activeProzessId,
  })

  // ── Mutations ─────────────────────────────────────────────────────────
  const startenMutation = useMutation({
    mutationFn: () => prozesseApi.starten(neuerTyp, neuerObjektId || undefined),
    onSuccess: (p) => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['prozesse'] })
      setActiveProzessId(p.id)
      setCurrentNr(p.current_step ?? 1)
      setStepErrors([])
      setEwAbschlussErgebnis(null)
    },
    onError: (err: unknown) => {
      const msgs = extractErrors(err)
      setMutationError(msgs[0])
    },
  })

  const saveStepMutation = useMutation({
    mutationFn: ({ nr, daten }: { nr: number; daten: Record<string, unknown> }) =>
      prozesseApi.saveStep(activeProzessId!, nr, daten),
    onSuccess: () => {
      setStepErrors([])
      queryClient.invalidateQueries({ queryKey: ['prozess', activeProzessId] })
    },
    onError: (err: unknown) => {
      setStepErrors(extractErrors(err))
    },
  })

  const abschliessenMutation = useMutation({
    mutationFn: () => prozesseApi.abschliessen(activeProzessId!),
    onSuccess: (data) => {
      setStepErrors([])
      queryClient.invalidateQueries({ queryKey: ['prozesse'] })
      queryClient.invalidateQueries({ queryKey: ['prozess', activeProzessId] })
      const ewResult = data as { wechsel_id?: string }
      if (ewResult?.wechsel_id) {
        setEwAbschlussErgebnis(data as EWAbschlussErgebnis)
        return
      }
      const objId = (data as { objekt_id?: string })?.objekt_id ?? (data as { objekt?: string })?.objekt
      if (objId) {
        navigate(`/objekte/${objId}`)
      }
    },
    onError: (err: unknown) => {
      setStepErrors(extractErrors(err))
    },
  })

  const abbrechenMutation = useMutation({
    mutationFn: () => prozesseApi.abbrechen(activeProzessId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prozesse'] })
      setActiveProzessId(null)
      setCurrentNr(1)
      setStepErrors([])
      setEwAbschlussErgebnis(null)
    },
  })

  // ── Wizard logic ──────────────────────────────────────────────────────
  const stepsData = {
    ...(aktiverProzess?.steps_data ?? {}),
    objekt_id: aktiverProzess?.objekt,
  } as Record<string, unknown>
  const isEw = aktiverProzess?.prozess_typ === 'eigentuemerwechsel'
  const stepLabels = isEw ? EW_STEP_LABELS : STEP_LABELS
  const totalSteps = stepLabels.length

  function getStepInitialData(nr: number): Record<string, unknown> {
    // Backend may store step data as "1", "2", … or "step_1", "step_2", …
    const key1 = String(nr)
    const key2 = `step_${nr}`
    const d = stepsData[key1] ?? stepsData[key2]
    return (d as Record<string, unknown>) ?? {}
  }

  const handleWeiter = async (daten: Record<string, unknown>): Promise<void> => {
    if (currentNr === totalSteps) {
      await abschliessenMutation.mutateAsync()
      return
    }
    await saveStepMutation.mutateAsync({ nr: currentNr, daten })
    await refetchAktiverProzess()
    setCurrentNr(prev => Math.min(prev + 1, totalSteps))
  }

  const handleZurueck = () => {
    setStepErrors([])
    setCurrentNr(prev => Math.max(prev - 1, 1))
  }

  const handleStepClick = (nr: number) => {
    // Only allow clicking on already completed steps
    if (nr < (aktiverProzess?.current_step ?? 1)) {
      setStepErrors([])
      setCurrentNr(nr)
    }
  }

  // ── Active wizard view ────────────────────────────────────────────────
  if (activeProzessId && aktiverProzess) {
    // EW success view
    if (aktiverProzess.status === 'abgeschlossen' && ewAbschlussErgebnis) {
      return (
        <div className="max-w-2xl mx-auto">
          <div className="bg-white rounded-lg border border-green-200 p-8 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto">
              <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-900">Eigentümerwechsel erfolgreich durchgeführt</h2>
            <p className="text-sm text-gray-500">Der Wechsel wurde atomar in der Datenbank gespeichert.</p>
            <div className="rounded-lg bg-gray-50 border border-gray-200 p-4 text-sm text-left space-y-2 max-w-sm mx-auto">
              <div className="grid grid-cols-2 gap-1">
                <span className="text-gray-500">Vorgang-ID:</span>
                <span className="font-mono text-xs font-medium">{ewAbschlussErgebnis.wechsel_id}</span>
                <span className="text-gray-500">Käufer-EV:</span>
                <span className="font-mono text-xs font-medium">{ewAbschlussErgebnis.kaeufer_ev_id}</span>
                {ewAbschlussErgebnis.auszahlungslauf_id && (
                  <>
                    <span className="text-gray-500">Auszahlungslauf:</span>
                    <span className="font-mono text-xs font-medium">{ewAbschlussErgebnis.auszahlungslauf_id}</span>
                  </>
                )}
                <span className="text-gray-500">Storniert:</span>
                <span className="font-medium">{ewAbschlussErgebnis.storniert_count} Sollstellung(en)</span>
                <span className="text-gray-500">Nachgeholt:</span>
                <span className="font-medium">{ewAbschlussErgebnis.nachhol_count} Sollstellung(en)</span>
              </div>
            </div>
            <div className="flex gap-3 justify-center pt-2">
              <Button onClick={() => { setActiveProzessId(null); setEwAbschlussErgebnis(null) }}>
                Zu den Prozessen
              </Button>
            </div>
          </div>
        </div>
      )
    }

    const processCurrentStep = aktiverProzess.current_step ?? 1
    const stepperSchritte = buildStepperSchritte(stepLabels, currentNr, processCurrentStep)
    const initialData = getStepInitialData(currentNr)
    const isMutating = saveStepMutation.isPending || abschliessenMutation.isPending

    const stepProps: StepProps = {
      prozessId: activeProzessId,
      stepsData,
      initialData,
      onWeiter: handleWeiter,
      isLoading: isMutating,
      errors: stepErrors,
    }

    let stepComponents: Record<number, React.ReactElement>
    if (isEw) {
      stepComponents = {
        1: <EW_Step01_EinheitStichtag   key={1} {...stepProps} />,
        2: <EW_Step02_Kaeufer           key={2} {...stepProps} />,
        3: <EW_Step03_HausgeldSollwerte key={3} {...stepProps} />,
        4: <EW_Step04_Analyse           key={4} {...stepProps} />,
        5: <EW_Step05_Vorschau          key={5} {...stepProps} />,
      }
    } else {
      stepComponents = {
        1:  <Step01_Objekttyp        key={1}  {...stepProps} />,
        2:  <Step02_Stammdaten       key={2}  {...stepProps} />,
        3:  <Step03_Eingaenge        key={3}  {...stepProps} />,
        4:  <Step04a_Wirtschaftsjahr key={4}  {...stepProps} />,
        5:  <Step04_Einheiten        key={5}  {...stepProps} />,
        6:  <Step06_Bankkonten       key={6}  {...stepProps} />,
        7:  <Step07_Kontenrahmen     key={7}  {...stepProps} />,
        8:  <Step08_Vertraege        key={8}  {...stepProps} />,
        9:  <Step09_Freigabelimits   key={9}  {...stepProps} />,
        10: <Step10_Review           key={10} {...stepProps} />,
      }
    }

    const currentStepLabel = stepLabels.find(s => s.nr === currentNr)?.bezeichnung ?? ''

    return (
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={() => setActiveProzessId(null)}
            className="text-sm text-primary-600 hover:underline flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Alle Prozesse
          </button>
          <div className="flex items-center gap-3">
            <Badge value={aktiverProzess.status} />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => abbrechenMutation.mutate()}
              disabled={abbrechenMutation.isPending}
              className="text-red-600 hover:bg-red-50"
            >
              Abbrechen
            </Button>
          </div>
        </div>

        {/* Header */}
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
          <div className="flex items-start justify-between mb-1">
            <div>
              <h2 className="text-lg font-bold text-gray-900">{aktiverProzess.prozess_typ_display}</h2>
              {aktiverProzess.objekt && (() => {
                const obj = objekte?.find(o => o.id === aktiverProzess.objekt)
                return obj ? (
                  <p className="text-sm text-primary-700 font-medium mt-0.5">
                    Objekt: {obj.objektnummer} — {obj.bezeichnung}
                  </p>
                ) : null
              })()}
              <p className="text-sm text-gray-500 mt-0.5">
                Schritt {currentNr} von {stepLabels.length}: <span className="font-medium text-gray-700">{currentStepLabel}</span>
              </p>
            </div>
          </div>
        </div>

        {/* Stepper */}
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
          <Stepper
            schritte={stepperSchritte}
            onStepClick={handleStepClick}
          />
        </div>

        {/* Step content */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-800 mb-4">
            {currentNr}. {currentStepLabel}
          </h3>

          {stepComponents[currentNr] ?? (
            <p className="text-sm text-gray-400">Unbekannter Schritt {currentNr}</p>
          )}

          {currentNr > 1 && (
            <div className="flex mt-4 pt-4 border-t border-gray-100">
              <Button variant="secondary" size="sm" onClick={handleZurueck} disabled={isMutating}>
                ← Zurück
              </Button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ── List / Start view ─────────────────────────────────────────────────
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Prozesse & Wizards</h1>

      {/* Neuen Prozess starten */}
      <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6 max-w-xl">
        <h2 className="font-semibold text-gray-700 mb-4">Neuen Prozess starten</h2>
        <div className="flex flex-col gap-3">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">Prozess-Typ</label>
            <select
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={neuerTyp}
              onChange={e => setNeuerTyp(e.target.value as ProzessTyp)}
            >
              {PROZESS_TYPEN.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {neuerTyp !== 'objekt_anlegen' && (
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Objekt</label>
              <select
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={neuerObjektId}
                onChange={e => setNeuerObjektId(e.target.value)}
              >
                <option value="">Objekt wählen…</option>
                {objekte?.map(o => (
                  <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
                ))}
              </select>
            </div>
          )}

          {mutationError && (
            <p className="text-sm text-red-600">{mutationError}</p>
          )}

          <Button
            onClick={() => startenMutation.mutate()}
            disabled={startenMutation.isPending}
            className="self-start"
          >
            {startenMutation.isPending ? 'Startet…' : 'Prozess starten'}
          </Button>
        </div>
      </div>

      {/* Prozess-Liste */}
      {prozesseLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Typ</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Schritt</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Gestartet am</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Aktion</th>
              </tr>
            </thead>
            <tbody>
              {prozesse?.map(p => (
                <tr key={p.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">{p.prozess_typ_display}</td>
                  <td className="px-4 py-3 text-gray-600">{p.current_step}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {new Date(p.gestartet_am).toLocaleDateString('de-DE')}
                  </td>
                  <td className="px-4 py-3"><Badge value={p.status} /></td>
                  <td className="px-4 py-3">
                    {p.status === 'aktiv' && (
                      <button
                        onClick={() => {
                          setActiveProzessId(p.id)
                          setCurrentNr(p.current_step ?? 1)
                          setStepErrors([])
                          setEwAbschlussErgebnis(null)
                        }}
                        className="text-xs text-primary-600 hover:underline"
                      >
                        Fortsetzen
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {prozesse?.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    Noch keine Prozesse vorhanden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
