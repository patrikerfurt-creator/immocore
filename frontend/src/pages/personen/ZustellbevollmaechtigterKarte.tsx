import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { personenApi } from '../../api/personen'
import { Button } from '../../components/ui/Button'

/**
 * Zuordnung eines Zustellungsbevollmächtigten (Person-Typ 500) zu einem
 * Eigentümer/Mieter. Ist einer hinterlegt, gehen alle Schreiben, Mails und
 * PDFs nur noch an den Bevollmächtigten — der Eigentümer bleibt im System
 * erkennbar, erscheint im Schreiben selbst aber nicht mehr.
 */
function fehlertext(fehler: unknown, ersatz: string): string {
  return (fehler as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? ersatz
}

interface Props {
  personId: string
  aktuellId?: string | null
  aktuellName?: string | null
}

export function ZustellbevollmaechtigterKarte({ personId, aktuellId, aktuellName }: Props) {
  const queryClient = useQueryClient()
  const [auswahlOffen, setAuswahlOffen] = useState(false)
  const [gewaehlt, setGewaehlt] = useState('')
  const [fehler, setFehler] = useState('')

  // Auswahlliste aller Zustellungsbevollmächtigten (Typ 500).
  const { data: kandidaten, isLoading: ladeKandidaten } = useQuery({
    queryKey: ['personen', { typ: '500' }],
    queryFn: () => personenApi.list({ typ: '500' }),
    enabled: auswahlOffen,
  })

  function nachAktion() {
    setFehler('')
    setAuswahlOffen(false)
    setGewaehlt('')
    queryClient.invalidateQueries({ queryKey: ['person', personId] })
  }

  const setzen = useMutation({
    mutationFn: (zbId: string | null) => personenApi.linkZustellbevollmaechtigter(personId, zbId),
    onSuccess: nachAktion,
    onError: (e) => setFehler(fehlertext(e, 'Die Zuordnung konnte nicht gespeichert werden.')),
  })

  const laeuft = setzen.isPending

  return (
    <div className="md:col-span-2 rounded-lg border border-gray-200 p-5 space-y-3">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
        Zustellungsbevollmächtigter
      </h2>

      {aktuellId ? (
        <>
          <p className="text-sm text-gray-700">
            Alle Schreiben, Mails und PDFs gehen an{' '}
            <Link to={`/personen/${aktuellId}`} className="font-medium text-blue-700 hover:underline">
              {aktuellName || 'Bevollmächtigten'}
            </Link>
            .
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              variant="secondary" size="sm" disabled={laeuft}
              onClick={() => setAuswahlOffen(true)}
            >
              Ändern
            </Button>
            <Button
              variant="danger" size="sm" disabled={laeuft}
              onClick={() => setzen.mutate(null)}
            >
              Entfernen
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-gray-500">
            Kein Zustellungsbevollmächtigter hinterlegt — die Zustellung erfolgt an
            die Person selbst.
          </p>
          {!auswahlOffen && (
            <Button size="sm" disabled={laeuft} onClick={() => setAuswahlOffen(true)}>
              Zustellungsbevollmächtigten zuordnen
            </Button>
          )}
        </>
      )}

      {auswahlOffen && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <select
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
            value={gewaehlt}
            onChange={(e) => setGewaehlt(e.target.value)}
            disabled={ladeKandidaten || laeuft}
          >
            <option value="">
              {ladeKandidaten ? 'Laden…' : 'Bitte wählen…'}
            </option>
            {(kandidaten ?? []).map((k) => (
              <option key={k.id} value={k.id}>
                {k.name} {k.personennummer ? `(${k.personennummer})` : ''}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            disabled={!gewaehlt || laeuft}
            onClick={() => setzen.mutate(gewaehlt)}
          >
            {laeuft ? 'Speichern…' : 'Übernehmen'}
          </Button>
          <Button
            variant="secondary" size="sm" disabled={laeuft}
            onClick={() => { setAuswahlOffen(false); setGewaehlt(''); setFehler('') }}
          >
            Abbrechen
          </Button>
          {!ladeKandidaten && (kandidaten ?? []).length === 0 && (
            <p className="text-sm text-amber-700">
              Es ist noch keine Person vom Typ „Zustellungsbevollmächtigter" angelegt.
            </p>
          )}
        </div>
      )}

      {fehler && <p className="text-sm text-red-600">{fehler}</p>}
    </div>
  )
}
