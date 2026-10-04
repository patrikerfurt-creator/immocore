import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { korrespondenzFehlerText, schreibenApi } from '../../../api/korrespondenz'
import { Badge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import type { SchreibenDetail } from '../../../types'
import { ANLASS_LABEL, KANAL_LABEL } from '../konstanten'
import { PdfAnzeige } from './PdfAnzeige'
import { SchreibenTextAnpassung } from './SchreibenTextAnpassung'
import {
  ANZEIGE_STATUS_BADGE, ANZEIGE_STATUS_LABEL, anzeigeStatus, datumZeit,
} from './schreibenKonstanten'

type Meldung = { art: 'ok' | 'fehler' | 'info'; text: string }

/** Beschreibt das Versandergebnis für den Mitarbeiter. */
export function versandMeldung(
  ergebnis: 'versendet' | 'druckstapel' | 'fehlgeschlagen', hinweis: string,
): Meldung {
  if (ergebnis === 'versendet') return { art: 'ok', text: 'Freigegeben und versendet.' }
  if (ergebnis === 'druckstapel') {
    return { art: 'info', text: `Freigegeben. Der Brief wartet im Druckstapel auf den Druck.${hinweis ? ` ${hinweis}` : ''}` }
  }
  return {
    art: 'fehler',
    text: `Freigegeben, aber der Versand ist fehlgeschlagen${hinweis ? `: ${hinweis}` : '.'} Ein Brief ist weiterhin möglich.`,
  }
}

const MELDUNG_KLASSE: Record<Meldung['art'], string> = {
  ok: 'border-green-200 bg-green-50 text-green-800',
  info: 'border-blue-200 bg-blue-50 text-blue-800',
  fehler: 'border-red-200 bg-red-50 text-red-700',
}

/** Prüfansicht eines Schreibens (Spec 7.2): fertige PDF-Vorschau, Textanpassung, Aktionen. */
export function SchreibenPruefungPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [pdfVersion, setPdfVersion] = useState(0)
  const [meldung, setMeldung] = useState<Meldung | null>(null)
  const [verwerfenFrage, setVerwerfenFrage] = useState(false)
  const [textOffen, setTextOffen] = useState(false)

  const { data: schreiben, isLoading, error } = useQuery({
    queryKey: ['korrespondenz-schreiben', 'detail', id],
    queryFn: () => schreibenApi.get(id!),
    enabled: !!id,
  })

  function aktualisiere(neu: SchreibenDetail) {
    qc.setQueryData(['korrespondenz-schreiben', 'detail', id], neu)
    qc.invalidateQueries({ queryKey: ['korrespondenz-schreiben', 'postausgang'] })
    setPdfVersion(v => v + 1)
  }
  const fehlerMeldung = async (e: unknown, fallback: string) =>
    setMeldung({ art: 'fehler', text: await korrespondenzFehlerText(e, fallback) })

  const freigeben = useMutation({
    mutationFn: () => schreibenApi.freigeben(id!),
    onMutate: () => setMeldung(null),
    onSuccess: neu => {
      aktualisiere(neu)
      setMeldung({ art: 'ok', text: 'Freigegeben. Das PDF ist im DMS abgelegt.' })
    },
    onError: e => fehlerMeldung(e, 'Freigabe nicht möglich.'),
  })

  const freigebenUndSenden = useMutation({
    mutationFn: async () => {
      const frei = await schreibenApi.freigeben(id!)
      aktualisiere(frei)
      try {
        return { versand: await schreibenApi.versenden(id!), sendeFehler: null as unknown }
      } catch (e) {
        return { versand: null, sendeFehler: e }
      }
    },
    onMutate: () => setMeldung(null),
    onSuccess: async ({ versand, sendeFehler }) => {
      if (versand) {
        aktualisiere(versand)
        setMeldung(versandMeldung(versand.versand.ergebnis, versand.versand.hinweis))
      } else {
        await fehlerMeldung(sendeFehler, 'Der Versand ist fehlgeschlagen.')
        setMeldung(m => m && { ...m, text: `Freigegeben, aber nicht gesendet: ${m.text}` })
      }
    },
    onError: e => fehlerMeldung(e, 'Freigabe nicht möglich.'),
  })

  const senden = useMutation({
    mutationFn: (kanal?: 'brief') => schreibenApi.versenden(id!, kanal),
    onMutate: () => setMeldung(null),
    onSuccess: neu => {
      aktualisiere(neu)
      setMeldung(versandMeldung(neu.versand.ergebnis, neu.versand.hinweis))
    },
    onError: e => fehlerMeldung(e, 'Versand nicht möglich.'),
  })

  const verwerfen = useMutation({
    mutationFn: () => schreibenApi.verwerfen(id!),
    onSuccess: neu => {
      aktualisiere(neu)
      navigate('/korrespondenz/postausgang')
    },
    onError: e => { setVerwerfenFrage(false); return fehlerMeldung(e, 'Verwerfen nicht möglich.') },
  })

  if (isLoading) return <p className="p-6 text-gray-400">Lade Schreiben…</p>
  if (error || !schreiben) return <p role="alert" className="p-6 text-red-600">Schreiben konnte nicht geladen werden.</p>

  const status = anzeigeStatus(schreiben)
  const laeuft = freigeben.isPending || freigebenUndSenden.isPending || senden.isPending || verwerfen.isPending
  const zurPruefung = schreiben.status === 'zur_pruefung'
  const kannVerwerfen = zurPruefung || status === 'nicht_erzeugbar'
  const hatPdf = ['zur_pruefung', 'freigegeben', 'versendet', 'versand_fehlgeschlagen'].includes(schreiben.status)
  const kannAnpassen = zurPruefung && schreiben.einzeln_bearbeitbar

  return (
    <div className="p-6 space-y-4 max-w-6xl">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/korrespondenz/postausgang" className="text-sm text-gray-500 hover:text-gray-800">← Postausgang</Link>
        <h1 className="text-xl font-semibold font-mono">{schreiben.nummer}</h1>
        <Badge value={ANZEIGE_STATUS_BADGE[status]} label={ANZEIGE_STATUS_LABEL[status]} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
            <h2 className="font-medium text-gray-800">{schreiben.betreff || 'Ohne Betreff'}</h2>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">Empfänger</dt><dd>{schreiben.empfaenger?.name ?? '–'}</dd>
              <dt className="text-gray-500">Objekt</dt><dd>{schreiben.objekt?.bezeichnung ?? '–'}</dd>
              <dt className="text-gray-500">Einheit</dt><dd>{schreiben.einheit?.einheit_nr ?? '–'}</dd>
              <dt className="text-gray-500">Vorlage</dt>
              <dd>{schreiben.vorlage.bezeichnung}<br /><span className="text-xs text-gray-400">{ANLASS_LABEL[schreiben.vorlage.anlass] ?? schreiben.vorlage.anlass}</span></dd>
              <dt className="text-gray-500">Kanal</dt>
              <dd>{KANAL_LABEL[schreiben.kanal as keyof typeof KANAL_LABEL] ?? schreiben.kanal}{schreiben.auch_brief && schreiben.kanal !== 'brief' ? ' + Brief' : ''}</dd>
              <dt className="text-gray-500">Erstellt</dt><dd>{datumZeit(schreiben.erstellt_am)}</dd>
              {schreiben.freigegeben_am && (<><dt className="text-gray-500">Freigegeben</dt><dd>{datumZeit(schreiben.freigegeben_am)}</dd></>)}
              {schreiben.versendet_am && (<><dt className="text-gray-500">Versendet</dt><dd>{datumZeit(schreiben.versendet_am)}</dd></>)}
            </dl>
            {schreiben.vorgang && (
              <Link to={`/vorgaenge/${schreiben.vorgang}`} className="text-sm text-primary-600 hover:underline">Zum Vorgang</Link>
            )}
          </div>

          {(status === 'nicht_erzeugbar' || status === 'versand_fehlgeschlagen') && schreiben.fehler && (
            <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <p className="font-medium">
                {status === 'nicht_erzeugbar' ? 'Nicht erzeugbar — Ursache:' : 'Versand fehlgeschlagen:'}
              </p>
              <p>{schreiben.fehler}</p>
            </div>
          )}

          {meldung && (
            <div role={meldung.art === 'fehler' ? 'alert' : 'status'}
              className={`rounded border p-3 text-sm ${MELDUNG_KLASSE[meldung.art]}`}>
              {meldung.text}
            </div>
          )}

          {/* Aktionen */}
          <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-2">
            <h2 className="font-medium text-gray-800">Aktionen</h2>
            {zurPruefung && (
              <div className="flex flex-wrap gap-2">
                <Button type="button" disabled={laeuft} onClick={() => freigeben.mutate()}>
                  {freigeben.isPending ? 'Gebe frei…' : 'Freigeben'}
                </Button>
                <Button type="button" disabled={laeuft} onClick={() => freigebenUndSenden.mutate()}>
                  {freigebenUndSenden.isPending ? 'Gebe frei und sende…' : 'Freigeben & Senden'}
                </Button>
              </div>
            )}
            {schreiben.status === 'freigegeben' && (
              <Button type="button" disabled={laeuft} onClick={() => senden.mutate(undefined)}>Senden</Button>
            )}
            {schreiben.status === 'versand_fehlgeschlagen' && (
              <div className="flex flex-wrap gap-2">
                <Button type="button" disabled={laeuft} onClick={() => senden.mutate(undefined)}>Erneut senden</Button>
                <Button type="button" variant="secondary" disabled={laeuft} onClick={() => senden.mutate('brief')}>
                  Als Brief senden
                </Button>
              </div>
            )}
            {kannVerwerfen && (
              verwerfenFrage ? (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span>Schreiben wirklich verwerfen?</span>
                  <Button type="button" variant="danger" size="sm" disabled={laeuft} onClick={() => verwerfen.mutate()}>
                    Ja, verwerfen
                  </Button>
                  <Button type="button" variant="secondary" size="sm" onClick={() => setVerwerfenFrage(false)}>Abbrechen</Button>
                </div>
              ) : (
                <Button type="button" variant="danger" disabled={laeuft} onClick={() => setVerwerfenFrage(true)}>
                  Verwerfen
                </Button>
              )
            )}
            {!zurPruefung && !kannVerwerfen && schreiben.status !== 'freigegeben' && schreiben.status !== 'versand_fehlgeschlagen' && (
              <p className="text-sm text-gray-500">Für dieses Schreiben sind keine Aktionen mehr möglich.</p>
            )}
          </div>

          {kannAnpassen && (
            <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-2">
              <button type="button" className="font-medium text-gray-800" aria-expanded={textOffen}
                onClick={() => setTextOffen(o => !o)}>
                {textOffen ? '▾' : '▸'} Text anpassen
              </button>
              {textOffen && <SchreibenTextAnpassung schreiben={schreiben} onGespeichert={aktualisiere} />}
            </div>
          )}
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-2">
          <h2 className="font-medium text-gray-800">Vorschau</h2>
          {hatPdf ? (
            <PdfAnzeige titel="Schreiben-Vorschau" dateiname={`${schreiben.nummer}.pdf`}
              laden={() => schreibenApi.pdf(schreiben.id)} neuLadenKey={`${schreiben.status}-${pdfVersion}`} />
          ) : (
            <p className="text-sm text-gray-500">Für dieses Schreiben gibt es keine Vorschau.</p>
          )}
        </div>
      </div>
    </div>
  )
}
