import type { Ampel } from '../../types'

const FARBE: Record<Ampel, string> = {
  gruen: 'bg-green-500',
  gelb: 'bg-yellow-400',
  rot: 'bg-red-500',
}

const LABEL: Record<Ampel, string> = {
  gruen: 'Grün — belastbar',
  gelb: 'Gelb — bitte prüfen',
  rot: 'Rot — Korrektur nötig',
}

/** Kleiner Ampelpunkt (je Feld) oder großer Punkt mit Gesamt-% (oben im Formular). */
export function Ampelpunkt({
  ampel,
  gross = false,
  konfidenz,
  title,
}: {
  ampel: Ampel | null
  gross?: boolean
  konfidenz?: number | null
  title?: string
}) {
  const farbe = ampel ? FARBE[ampel] : 'bg-gray-300'
  const size = gross ? 'w-5 h-5' : 'w-3 h-3'
  return (
    <span className="inline-flex items-center gap-2" title={title ?? (ampel ? LABEL[ampel] : 'Noch nicht bewertet')}>
      <span className={`inline-block rounded-full ${size} ${farbe}`} />
      {gross && (
        <span className="text-sm font-medium text-gray-700">
          {ampel ? LABEL[ampel] : 'Noch nicht bewertet'}
          {konfidenz != null && ` · ${Number(konfidenz).toFixed(0)} %`}
        </span>
      )}
    </span>
  )
}
