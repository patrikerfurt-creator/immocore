import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi } from '../../api/wirtschaftsplan'
import { Schritt2_Konten } from './wizard/Schritt2_Konten'
import { Schritt3_Verteilung } from './wizard/Schritt3_Verteilung'
import { Schritt4_HausgeldVorschau } from './wizard/Schritt4_HausgeldVorschau'
import { Schritt5_Beschluss } from './wizard/Schritt5_Beschluss'

const STEP_LABELS = ['Übersicht', 'Konten', 'Verteilung', 'Hausgeld-Vorschau', 'Beschluss']

export function WirtschaftsplanWizard() {
  const { wpId } = useParams<{ wpId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [step, setStep] = useState(2) // Start at Schritt 2 (Konten)
  const [errors, setErrors] = useState<string[]>([])

  const { data: wp, isLoading } = useQuery({
    queryKey: ['wirtschaftsplan', wpId],
    queryFn: () => wirtschaftsplanApi.get(wpId!),
    enabled: !!wpId,
    refetchInterval: false,
  })

  const beschlussMut = useMutation({
    mutationFn: (data: { beschluss_datum: string; top?: string; bemerkung?: string }) =>
      wirtschaftsplanApi.beschluss(wpId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wirtschaftsplaene'] })
      qc.invalidateQueries({ queryKey: ['wirtschaftsplan', wpId] })
      navigate(`/abrechnung-wp/wirtschaftsplan/${wpId}`)
    },
    onError: (err: any) => {
      setErrors(err.response?.data?.errors ?? ['Unbekannter Fehler.'])
    },
  })

  if (isLoading) return <div className="p-6 text-sm text-gray-400">Laden…</div>
  if (!wp) return <div className="p-6 text-sm text-red-500">Nicht gefunden.</div>

  if (wp.status !== 'entwurf') {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="rounded-md bg-blue-50 border border-blue-200 p-4 text-sm text-blue-700">
          Dieser Wirtschaftsplan ist bereits beschlossen. Für Änderungen einen Korrekturbeschluss erstellen.
        </div>
        <button
          onClick={() => navigate(`/abrechnung-wp/wirtschaftsplan/${wpId}`)}
          className="mt-4 text-sm text-primary-600 hover:underline"
        >
          ← Zurück zur Detailansicht
        </button>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Wirtschaftsplan bearbeiten</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {wp.objekt_bezeichnung} — WJ {wp.wj_jahr} — Wirkung ab {wp.wirkung_ab}
          </p>
        </div>
        <button
          onClick={() => navigate(`/abrechnung-wp/wirtschaftsplan/${wpId}`)}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          ✕ Schließen
        </button>
      </div>

      {/* Schritte-Navigation */}
      <div className="flex items-center gap-0 mb-8">
        {STEP_LABELS.map((label, i) => {
          const n = i + 1
          const active = n === step
          const done = n < step
          return (
            <div key={n} className="flex items-center flex-1 last:flex-none">
              <button
                onClick={() => { if (done || active) setStep(n) }}
                className={`flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full transition-colors ${
                  active
                    ? 'bg-primary-600 text-white'
                    : done
                    ? 'bg-primary-100 text-primary-700 hover:bg-primary-200 cursor-pointer'
                    : 'text-gray-400 cursor-default'
                }`}
              >
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                  active ? 'bg-white text-primary-600' : done ? 'bg-primary-600 text-white' : 'bg-gray-200 text-gray-500'
                }`}>{done ? '✓' : n}</span>
                {label}
              </button>
              {i < STEP_LABELS.length - 1 && (
                <div className={`flex-1 h-0.5 mx-1 ${done ? 'bg-primary-400' : 'bg-gray-200'}`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Schritt-Inhalt */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        {errors.length > 0 && (
          <div className="mb-4 rounded-md bg-red-50 p-3">
            {errors.map((e, i) => <p key={i} className="text-sm text-red-600">{e}</p>)}
          </div>
        )}

        {step === 1 && (
          <div>
            <h2 className="text-base font-semibold text-gray-800 mb-4">Übersicht</h2>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div><span className="text-gray-500">Wirtschaftsjahr:</span> <strong>WJ {wp.wj_jahr}</strong></div>
              <div><span className="text-gray-500">Wirkung ab:</span> <strong>{wp.wirkung_ab}</strong></div>
              <div><span className="text-gray-500">Status:</span> <strong>{wp.status}</strong></div>
              <div><span className="text-gray-500">Gesamtsumme:</span> <strong>
                {parseFloat(wp.gesamtsumme).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
              </strong></div>
            </div>
            <div className="flex justify-end mt-6">
              <button
                onClick={() => setStep(2)}
                className="bg-primary-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-primary-700"
              >
                Weiter →
              </button>
            </div>
          </div>
        )}

        {step === 2 && wp && (
          <Schritt2_Konten
            wp={wp}
            onWeiter={() => { qc.invalidateQueries({ queryKey: ['wirtschaftsplan', wpId] }); setStep(3) }}
            onZurueck={() => setStep(1)}
          />
        )}

        {step === 3 && wp && (
          <Schritt3_Verteilung
            wp={wp}
            onWeiter={() => { qc.invalidateQueries({ queryKey: ['wirtschaftsplan', wpId] }); setStep(4) }}
            onZurueck={() => setStep(2)}
          />
        )}

        {step === 4 && wp && (
          <Schritt4_HausgeldVorschau
            wp={wp}
            onWeiter={() => setStep(5)}
            onZurueck={() => setStep(3)}
          />
        )}

        {step === 5 && wp && (
          <Schritt5_Beschluss
            wp={wp}
            isLoading={beschlussMut.isPending}
            errors={errors}
            onSaveEntwurf={() => navigate(`/abrechnung-wp/wirtschaftsplan/${wpId}`)}
            onBeschluss={(data) => { setErrors([]); beschlussMut.mutate(data) }}
            onZurueck={() => setStep(4)}
          />
        )}
      </div>
    </div>
  )
}
