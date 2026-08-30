import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DublettenKandidat,
  KreditorDublettenPruefung,
  kreditorDublettenApi,
} from '../../api/kreditorDubletten'
import { Button } from '../../components/ui/Button'

/**
 * Prüfliste für angehaltene Kreditor-Neuanlagen.
 *
 * Solange ein Fall offen ist, hat die zugehörige Rechnung keinen Kreditor
 * und kann nicht gebucht werden — die Liste ist damit eine echte
 * Arbeitsliste, kein Hinweiskasten.
 */
const ANLASS_STIL: Record<string, string> = {
  iban_abweichung: 'bg-red-100 text-red-800',
  name_abweichung: 'bg-orange-100 text-orange-800',
  fuzzy_name: 'bg-yellow-100 text-yellow-800',
}

const ANLASS_ERKLAERUNG: Record<string, string> = {
  iban_abweichung:
    'Der Name ist bekannt, die Bankverbindung weicht ab. Bitte besonders sorgfältig prüfen — '
    + 'eine geänderte IBAN bei bekanntem Lieferanten ist das typische Muster bei Rechnungsbetrug.',
  name_abweichung:
    'Die Bankverbindung ist bekannt, der Firmenname weicht ab. Möglich bei Umfirmierung — '
    + 'oder ein Hinweis darauf, dass die Rechnung nicht von diesem Lieferanten stammt.',
  fuzzy_name:
    'Der Name ähnelt einem bestehenden Kreditor. Vermutlich dieselbe Firma in anderer Schreibweise.',
}

function betrag(wert: string | null): string {
  if (!wert) return '—'
  return Number(wert).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
}

function ibanFormatiert(iban: string): string {
  return iban ? iban.replace(/(.{4})/g, '$1 ').trim() : '—'
}

function fehlertext(fehler: unknown, ersatz: string): string {
  return (fehler as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? ersatz
}

function KandidatZeile({
  kandidat, erkannteIban, onZuordnen, deaktiviert,
}: {
  kandidat: DublettenKandidat
  erkannteIban: string
  onZuordnen: (kreditorId: string, ibanUebernehmen: boolean) => void
  deaktiviert: boolean
}) {
  // Nur anbieten, wenn die IBAN überhaupt neu ist — sonst führt der Haken
  // in die Irre.
  const ibanIstNeu = Boolean(erkannteIban) && erkannteIban !== kandidat.iban
  const [ibanUebernehmen, setIbanUebernehmen] = useState(true)

  return (
    <li className="border border-gray-200 rounded-lg p-3 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-900">
            {kandidat.name}
            {!kandidat.aktiv && (
              <span className="ml-2 text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">
                deaktiviert
              </span>
            )}
          </p>
          <p className="text-xs text-gray-500 font-mono">
            {kandidat.kreditorennummer || 'ohne Nummer'} · {ibanFormatiert(kandidat.iban)}
          </p>
        </div>
        <span className="text-xs text-gray-500 whitespace-nowrap">
          {Math.round(kandidat.score * 100)} % · {kandidat.match_typ}
        </span>
      </div>

      {ibanIstNeu && (
        <label className="flex items-center gap-2 text-xs text-gray-600">
          <input
            type="checkbox"
            checked={ibanUebernehmen}
            onChange={e => setIbanUebernehmen(e.target.checked)}
          />
          Neue IBAN als weitere Bankverbindung hinterlegen
        </label>
      )}

      <div>
        <Button
          size="sm" variant="secondary" disabled={deaktiviert}
          onClick={() => onZuordnen(kandidat.id, ibanUebernehmen)}
        >
          Diesem Kreditor zuordnen
        </Button>
      </div>
    </li>
  )
}

function PruefKarte({ pruefung }: { pruefung: KreditorDublettenPruefung }) {
  const queryClient = useQueryClient()
  const [notiz, setNotiz] = useState('')
  const [fehler, setFehler] = useState('')

  function erledigt() {
    setFehler('')
    queryClient.invalidateQueries({ queryKey: ['kreditor-dubletten'] })
  }

  const zuordnen = useMutation({
    mutationFn: ({ kreditorId, iban }: { kreditorId: string; iban: boolean }) =>
      kreditorDublettenApi.zuordnen(pruefung.id, kreditorId, iban, notiz),
    onSuccess: erledigt,
    onError: e => setFehler(fehlertext(e, 'Die Zuordnung ist fehlgeschlagen.')),
  })

  const neuAnlegen = useMutation({
    mutationFn: () => kreditorDublettenApi.alsNeuAnlegen(pruefung.id, notiz),
    onSuccess: erledigt,
    onError: e => setFehler(fehlertext(e, 'Der Kreditor konnte nicht angelegt werden.')),
  })

  const ablehnen = useMutation({
    mutationFn: () => kreditorDublettenApi.ablehnen(pruefung.id, notiz),
    onSuccess: erledigt,
    onError: e => setFehler(fehlertext(e, 'Die Ablehnung ist fehlgeschlagen.')),
  })

  const laeuft = zuordnen.isPending || neuAnlegen.isPending || ablehnen.isPending

  return (
    <section className="bg-white rounded-xl border border-gray-200 shadow-sm">
      <header className="px-5 py-4 border-b border-gray-100 flex items-start justify-between gap-4">
        <div>
          <p className="text-base font-semibold text-gray-900">{pruefung.erkannter_name}</p>
          <p className="text-sm text-gray-500 font-mono">{ibanFormatiert(pruefung.erkannte_iban)}</p>
          <p className="text-xs text-gray-500 mt-1">
            Rechnung {pruefung.rechnungsnummer || pruefung.rechnung_dateiname}
            {pruefung.rechnungsdatum && ` vom ${new Date(pruefung.rechnungsdatum).toLocaleDateString('de-DE')}`}
            {' · '}{betrag(pruefung.betrag_brutto)}
          </p>
        </div>
        <span className={`text-xs font-medium px-2 py-1 rounded whitespace-nowrap ${ANLASS_STIL[pruefung.anlass] ?? 'bg-gray-100 text-gray-700'}`}>
          {pruefung.anlass_text}
        </span>
      </header>

      <div className="px-5 py-4 flex flex-col gap-4">
        <p className="text-sm text-gray-600">{ANLASS_ERKLAERUNG[pruefung.anlass]}</p>

        <div>
          <p className="text-sm font-medium text-gray-700 mb-2">
            Bestehende Kreditoren, die infrage kommen
          </p>
          <ul className="flex flex-col gap-2">
            {pruefung.kandidaten.map(k => (
              <KandidatZeile
                key={k.id}
                kandidat={k}
                erkannteIban={pruefung.erkannte_iban}
                deaktiviert={laeuft}
                onZuordnen={(kreditorId, iban) => zuordnen.mutate({ kreditorId, iban })}
              />
            ))}
          </ul>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Notiz (optional)</label>
          <input
            value={notiz}
            onChange={e => setNotiz(e.target.value)}
            placeholder="Warum wurde so entschieden?"
            className="rounded border border-gray-300 px-3 py-2 text-sm outline-none
                       focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          />
        </div>

        {fehler && <p className="text-sm text-red-600">{fehler}</p>}

        <div className="flex flex-wrap gap-2 pt-1 border-t border-gray-100">
          <Button disabled={laeuft} onClick={() => neuAnlegen.mutate()}>
            Als neuen Kreditor anlegen
          </Button>
          <Button variant="danger" disabled={laeuft} onClick={() => ablehnen.mutate()}>
            Rechnung ablehnen
          </Button>
        </div>
      </div>
    </section>
  )
}

export default function KreditorDubletten() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['kreditor-dubletten'],
    queryFn: () => kreditorDublettenApi.list(),
  })

  if (isLoading) return <p className="text-sm text-gray-500">Wird geladen…</p>
  if (isError) return <p className="text-sm text-red-600">Die Liste konnte nicht geladen werden.</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Kreditor-Prüfung</h1>
        <p className="text-sm text-gray-500 mt-1">
          Beim Rechnungsimport angehaltene Kreditoren. Solange ein Fall offen ist,
          hat die Rechnung keinen Kreditor und kann nicht gebucht werden.
        </p>
      </div>

      {!data?.length ? (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <p className="text-sm text-gray-600">Keine offenen Prüffälle.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          {data.map(p => <PruefKarte key={p.id} pruefung={p} />)}
        </div>
      )}
    </div>
  )
}
