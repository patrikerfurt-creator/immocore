const variants: Record<string, string> = {
  // Status allgemein
  aktiv:          'bg-green-100 text-green-800',
  archiviert:     'bg-gray-100 text-gray-600',
  // Buchung
  gebucht:        'bg-green-100 text-green-800',
  entwurf:        'bg-yellow-100 text-yellow-800',
  storniert:      'bg-red-100 text-red-800',
  // Rechnung
  erfasst:        'bg-gray-100 text-gray-700',
  in_pruefung:    'bg-blue-100 text-blue-700',
  freigegeben:    'bg-green-100 text-green-800',
  abgelehnt:      'bg-red-100 text-red-700',
  bezahlt:        'bg-emerald-100 text-emerald-800',
  // Prozess
  abgeschlossen:  'bg-green-100 text-green-800',
  abgebrochen:    'bg-red-100 text-red-700',
  // Ticket
  offen:          'bg-blue-100 text-blue-700',
  in_bearbeitung: 'bg-yellow-100 text-yellow-800',
  erledigt:       'bg-green-100 text-green-800',
  geschlossen:    'bg-gray-100 text-gray-600',
  // Priorität
  niedrig:        'bg-gray-100 text-gray-600',
  mittel:         'bg-yellow-100 text-yellow-700',
  hoch:           'bg-orange-100 text-orange-700',
  kritisch:       'bg-red-100 text-red-700',
}

export function Badge({ value, label }: { value: string; label?: string }) {
  const cls = variants[value] ?? 'bg-gray-100 text-gray-700'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {label ?? value}
    </span>
  )
}
