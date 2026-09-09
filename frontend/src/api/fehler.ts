/**
 * Lesbare Fehlermeldung aus einer axios-Fehlerantwort.
 *
 * axios' `error.message` ist immer nur "Request failed with status code 400" —
 * der eigentliche Grund steckt im Response-Body. DRF liefert dort je nach
 * Fehlerart `{error: …}`, `{detail: …}`, eine Liste oder ein Feld-Dict
 * (`{kontonummer: ["…"], non_field_errors: ["…"]}`). Alle Varianten werden hier
 * zu einem Satz zusammengefasst, damit der Anwender sieht was zu korrigieren ist.
 */
export function apiFehler(err: unknown, fallback = 'Unbekannter Fehler'): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data

  if (typeof data === 'string' && data.trim()) return data.trim()

  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    for (const key of ['error', 'detail']) {
      if (typeof d[key] === 'string') return d[key] as string
    }

    // Feld-Dict eines Serializers: "kontonummer: … | Konto existiert bereits"
    const teile: string[] = []
    for (const [feld, wert] of Object.entries(d)) {
      const text = Array.isArray(wert) ? wert.map(String).join(' ') : String(wert)
      if (!text) continue
      teile.push(feld === 'non_field_errors' || feld === 'detail' ? text : `${feld}: ${text}`)
    }
    if (teile.length) return teile.join(' | ')
  }

  return (err as Error)?.message || fallback
}
