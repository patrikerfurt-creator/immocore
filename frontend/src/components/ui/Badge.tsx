const variants: Record<string, string> = {
  // Status allgemein
  aktiv:          'bg-green-100 text-green-800',
  archiviert:     'bg-gray-100 text-gray-600',
  // Kontoumsatz (E-Banking)
  importiert:     'bg-gray-100 text-gray-700',
  erkannt:        'bg-blue-100 text-blue-700',
  vorschlag:      'bg-yellow-100 text-yellow-800',
  unklar:         'bg-red-100 text-red-700',
  verbucht:       'bg-green-100 text-green-800',
  // Kontoumsatz (Legacy)
  manuell:        'bg-purple-100 text-purple-700',
  ignoriert:      'bg-gray-100 text-gray-400',
  unbekannt:      'bg-orange-100 text-orange-700',
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
  // Hausgeld-Lauf
  vorschau:       'bg-yellow-100 text-yellow-800',
  commited:       'bg-green-100 text-green-800',
  // Prozess
  abgeschlossen:  'bg-green-100 text-green-800',
  abgebrochen:    'bg-red-100 text-red-700',
  // Ticket
  offen:          'bg-blue-100 text-blue-700',
  in_bearbeitung: 'bg-yellow-100 text-yellow-800',
  erledigt:       'bg-green-100 text-green-800',
  geschlossen:    'bg-gray-100 text-gray-600',
  // WKZ
  eingereicht:    'bg-orange-100 text-orange-800',
  aktiv:          'bg-green-100 text-green-800',
  pausiert:       'bg-yellow-100 text-yellow-800',
  beendet:        'bg-gray-100 text-gray-500',
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
