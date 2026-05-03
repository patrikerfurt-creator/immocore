import React from 'react'

export interface StepperStep {
  nr: number
  bezeichnung: string
  status: 'abgeschlossen' | 'aktiv' | 'ausstehend' | 'fehler'
}

interface StepperProps {
  schritte: StepperStep[]
  onStepClick?: (nr: number) => void
}

function stepCircleClass(status: StepperStep['status']): string {
  switch (status) {
    case 'abgeschlossen':
      return 'bg-green-600 border-green-600 text-white'
    case 'aktiv':
      return 'bg-primary-600 border-primary-600 text-white ring-4 ring-primary-100'
    case 'fehler':
      return 'bg-red-600 border-red-600 text-white'
    default:
      return 'bg-white border-gray-300 text-gray-400'
  }
}

function stepLabelClass(status: StepperStep['status']): string {
  switch (status) {
    case 'abgeschlossen':
      return 'text-green-700 font-medium'
    case 'aktiv':
      return 'text-primary-700 font-semibold'
    case 'fehler':
      return 'text-red-700 font-medium'
    default:
      return 'text-gray-400'
  }
}

function connectorClass(status: StepperStep['status']): string {
  return status === 'abgeschlossen' ? 'bg-green-400' : 'bg-gray-200'
}

export function Stepper({ schritte, onStepClick }: StepperProps) {
  return (
    <>
      {/* Horizontal layout for md+ screens */}
      <div className="hidden md:flex items-start w-full overflow-x-auto pb-2">
        {schritte.map((schritt, idx) => (
          <React.Fragment key={schritt.nr}>
            <div className="flex flex-col items-center flex-shrink-0" style={{ minWidth: '64px' }}>
              <button
                type="button"
                onClick={() => onStepClick?.(schritt.nr)}
                className={`w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm font-semibold transition-all ${stepCircleClass(schritt.status)} ${onStepClick ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}
                disabled={!onStepClick}
                aria-current={schritt.status === 'aktiv' ? 'step' : undefined}
              >
                {schritt.status === 'abgeschlossen' ? (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  schritt.nr
                )}
              </button>
              <span className={`mt-1 text-xs text-center leading-tight max-w-[72px] ${stepLabelClass(schritt.status)}`}>
                {schritt.bezeichnung}
              </span>
            </div>
            {idx < schritte.length - 1 && (
              <div className={`flex-1 h-0.5 mt-4 mx-1 min-w-[8px] ${connectorClass(schritt.status)}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Vertical layout for small screens */}
      <div className="flex md:hidden flex-col gap-0">
        {schritte.map((schritt, idx) => (
          <div key={schritt.nr} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <button
                type="button"
                onClick={() => onStepClick?.(schritt.nr)}
                className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-semibold transition-all ${stepCircleClass(schritt.status)} ${onStepClick ? 'cursor-pointer' : 'cursor-default'}`}
                disabled={!onStepClick}
              >
                {schritt.status === 'abgeschlossen' ? (
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  schritt.nr
                )}
              </button>
              {idx < schritte.length - 1 && (
                <div className={`w-0.5 h-6 ${connectorClass(schritt.status)}`} />
              )}
            </div>
            <span className={`mt-1 text-sm leading-tight ${stepLabelClass(schritt.status)}`}>
              {schritt.bezeichnung}
            </span>
          </div>
        ))}
      </div>
    </>
  )
}
