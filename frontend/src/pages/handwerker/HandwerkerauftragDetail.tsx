import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { handwerkerApi } from '../../api/handwerker'
import { objekteApi } from '../../api/objekte'
import { rechnungenApi } from '../../api/rechnungen'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { HandwerkerauftragStatus } from '../../types'
import {
  HWA_EREIGNIS_LABEL, HWA_MANUELLE_UEBERGAENGE, HWA_STATUS_LABEL,
  fehlerText, formatDatum, formatDatumZeit, formatGeld,
} from './shared'

export function HandwerkerauftragDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()

  const [kommentarText, setKommentarText] = useState('')
  const [zielStatus, setZielStatus] = useState<HandwerkerauftragStatus | null>(null)
  const [abschlussNotiz, setAbschlussNotiz] = useState('')
  const [rechnungAuswahl, setRechnungAuswahl] = useState('')

  const { data: auftrag, isLoading, error } = useQuery({
    queryKey: ['handwerkerauftrag', id],
    queryFn: () => handwerkerApi.get(id!),
    enabled: !!id,
  })

  const { data: objekt } = useQuery({
    queryKey: ['objekte', auftrag?.objekt],
    queryFn: () => objekteApi.get(auftrag!.objekt),
    enabled: !!auftrag?.objekt,
  })

  const { data: kreditor } = useQuery({
    queryKey: ['kreditor', auftrag?.kreditor],
    queryFn: () => rechnungenApi.getKreditor(auftrag!.kreditor),
    enabled: !!auftrag?.kreditor,
  })

  // Für die Rechnungszuordnung nach dem Kreditor des Auftrags vorgefiltert.
  const { data: kreditorRechnungen } = useQuery({
    queryKey: ['rechnungen-fuer-kreditor', auftrag?.kreditor],
    queryFn: () => rechnungenApi.list({ kreditor: auftrag!.kreditor }),
    enabled: !!auftrag?.kreditor,
  })

  const statusMutation = useMutation({
    mutationFn: (payload: { status: HandwerkerauftragStatus; abschluss_notiz?: string }) =>
      handwerkerApi.statusWechseln(id!, payload.status, undefined, payload.abschluss_notiz),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['handwerkerauftrag', id] })
      setZielStatus(null)
      setAbschlussNotiz('')
    },
  })

  const kommentarMutation = useMutation({
    mutationFn: (text: string) => handwerkerApi.kommentieren(id!, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['handwerkerauftrag', id] })
      setKommentarText('')
    },
  })

  const erneutVersendenMutation = useMutation({
    mutationFn: () => handwerkerApi.erneutVersenden(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['handwerkerauftrag', id] }),
  })

  const rechnungZuordnenMutation = useMutation({
    mutationFn: (rechnungId: string) => handwerkerApi.rechnungZuordnen(id!, rechnungId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['handwerkerauftrag', id] })
      setRechnungAuswahl('')
    },
  })

  const rechnungLoesenMutation = useMutation({
    mutationFn: (rechnungId: string) => handwerkerApi.rechnungLoesen(id!, rechnungId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['handwerkerauftrag', id] }),
  })

  if (isLoading) return <p className="p-4 text-gray-400">Lade Auftrag…</p>
  if (error || !auftrag) return <p className="p-4 text-red-600">Fehler beim Laden.</p>

  // Knöpfe im UI aus der MANUELLEN Übergangsmenge (nicht aus der vollen
  // Service-Tabelle) — siehe Begründung in shared.ts (Phase-D-Abnahme, Fehler 1).
  const erlaubteZiele = HWA_MANUELLE_UEBERGAENGE[auftrag.status] ?? []
  // Aus 'entwurf' (erster Versand ist fehlgeschlagen), 'versendet' und
  // 'abgelaufen' ist der (erneute) Versand die fachlich richtige Aktion.
  const darfVersenden = auftrag.status === 'entwurf' || auftrag.status === 'abgelaufen' || auftrag.status === 'versendet'
  const versandLabel = auftrag.status === 'entwurf' ? 'Auftragsmail senden' : 'Auftragsmail erneut senden'

  const tokenAbgelaufen = auftrag.token_status
    && auftrag.token_status.verbraucht_am === null
    && new Date(auftrag.token_status.gueltig_bis).getTime() <= Date.now()

  const zugeordneteIds = new Set(auftrag.rechnungen.map(r => r.id))
  const auswaehlbareRechnungen = (kreditorRechnungen ?? []).filter(r => !zugeordneteIds.has(r.id))

  function statusKlick(ziel: HandwerkerauftragStatus) {
    if (ziel === 'abgeschlossen') {
      setZielStatus('abgeschlossen')
      return
    }
    statusMutation.mutate({ status: ziel })
  }

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/handwerker/auftraege" className="text-gray-500 hover:text-gray-800 text-sm">← Zurück</Link>
        <h1 className="text-xl font-semibold font-mono">{auftrag.nummer}</h1>
        <Badge value={auftrag.status} label={HWA_STATUS_LABEL[auftrag.status]} />
        <Badge value={auftrag.prioritaet} />
      </div>

      {/* Stammdaten */}
      <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
        <h2 className="font-medium text-gray-800">{auftrag.titel}</h2>
        {auftrag.beschreibung && <p className="text-sm text-gray-600 whitespace-pre-wrap">{auftrag.beschreibung}</p>}
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-gray-500">Objekt</dt>
            <dd>
              <Link to={`/objekte/${auftrag.objekt}`} className="text-primary-600 hover:underline">
                {auftrag.objekt_bezeichnung ?? '–'}
              </Link>
              {objekt && <div className="text-gray-500 text-xs">{objekt.strasse}, {objekt.plz} {objekt.ort}</div>}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Handwerker</dt>
            <dd>
              {auftrag.kreditor_name}
              {auftrag.kreditor_gewerke_bezeichnung && <span className="text-gray-400"> ({auftrag.kreditor_gewerke_bezeichnung})</span>}
              {kreditor && (
                <div className="text-gray-500 text-xs">
                  {kreditor.email && <div>{kreditor.email}</div>}
                  {kreditor.telefon && <div>{kreditor.telefon}</div>}
                  {kreditor.kontakt_person && <div>Ansprechpartner: {kreditor.kontakt_person}</div>}
                </div>
              )}
            </dd>
          </div>
          <div><dt className="text-gray-500">Gewünscht ab</dt><dd>{auftrag.gewuenscht_ab ?? '–'}</dd></div>
          <div><dt className="text-gray-500">Geschätzte Kosten</dt><dd>{formatGeld(auftrag.geschaetzte_kosten)}</dd></div>
          {auftrag.vorgang && (
            <div>
              <dt className="text-gray-500">Vorgang</dt>
              <dd>
                <Link to={`/vorgaenge/${auftrag.vorgang.id}`} className="text-primary-600 hover:underline">
                  {auftrag.vorgang.nummer} — {auftrag.vorgang.betreff}
                </Link>
              </dd>
            </div>
          )}
          <div><dt className="text-gray-500">Erstellt</dt><dd>{formatDatumZeit(auftrag.erstellt_am)} von {auftrag.erstellt_von_name ?? '–'}</dd></div>
          {auftrag.ablehnung_grund && (
            <div className="col-span-2"><dt className="text-gray-500">Ablehnungsgrund</dt><dd>{auftrag.ablehnung_grund}</dd></div>
          )}
          {auftrag.abschluss_notiz && (
            <div className="col-span-2"><dt className="text-gray-500">Abschlussnotiz</dt><dd>{auftrag.abschluss_notiz}</dd></div>
          )}
        </dl>
      </div>

      {/* Token-Zustand (niemals den Token-Wert selbst — liefert die API bewusst nicht) */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-2">Bestätigungslink</h2>
        {!auftrag.token_status ? (
          <p className="text-sm text-gray-400">Kein Bestätigungslink vorhanden.</p>
        ) : auftrag.token_status.verbraucht_am ? (
          <p className="text-sm text-gray-600">Bereits verwendet am {formatDatumZeit(auftrag.token_status.verbraucht_am)}.</p>
        ) : tokenAbgelaufen ? (
          <p className="text-sm text-orange-700">Abgelaufen seit {formatDatumZeit(auftrag.token_status.gueltig_bis)}.</p>
        ) : (
          <p className="text-sm text-gray-600">Gültig bis {formatDatumZeit(auftrag.token_status.gueltig_bis)}.</p>
        )}

        {darfVersenden && (
          <div className="mt-3">
            <Button
              size="sm"
              variant="primary"
              disabled={erneutVersendenMutation.isPending}
              onClick={() => erneutVersendenMutation.mutate()}
            >
              {erneutVersendenMutation.isPending ? 'Wird versendet…' : versandLabel}
            </Button>
            {auftrag.status !== 'entwurf' && (
              <p className="text-xs text-gray-400 mt-1">
                Dadurch wird ein neuer Bestätigungslink erzeugt — ein zuvor versendeter Link wird sofort ungültig.
              </p>
            )}
            {erneutVersendenMutation.isError && (
              <p className="text-red-600 text-sm mt-1">{fehlerText(erneutVersendenMutation.error, 'Erneuter Versand fehlgeschlagen.')}</p>
            )}
          </div>
        )}
      </div>

      {/* Statuswechsel */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Status ändern</h2>
        {erlaubteZiele.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Übergänge mehr möglich (endgültiger Status).</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {erlaubteZiele.map(ziel => (
              <Button key={ziel} variant="secondary" size="sm" onClick={() => statusKlick(ziel)}>
                → {HWA_STATUS_LABEL[ziel]}
              </Button>
            ))}
          </div>
        )}
        {zielStatus === 'abgeschlossen' && (
          <div className="mt-3 space-y-2">
            <label className="text-sm font-medium text-gray-700 block">Abschlussnotiz (optional)</label>
            <textarea
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-20 resize-none"
              value={abschlussNotiz}
              onChange={e => setAbschlussNotiz(e.target.value)}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={statusMutation.isPending}
                onClick={() => statusMutation.mutate({ status: 'abgeschlossen', abschluss_notiz: abschlussNotiz || undefined })}
              >
                Bestätigen
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setZielStatus(null)}>Abbrechen</Button>
            </div>
          </div>
        )}
        {statusMutation.isError && (
          <p className="text-red-600 text-sm mt-2">{fehlerText(statusMutation.error, 'Statuswechsel fehlgeschlagen.')}</p>
        )}
      </div>

      {/* Rechnungszuordnung */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Zugeordnete Rechnungen</h2>
        <ul className="divide-y divide-gray-100 mb-3">
          {auftrag.rechnungen.map(r => (
            <li key={r.id} className="py-2 text-sm flex items-center justify-between">
              <span>
                {r.rechnungsnummer || '(ohne Nummer)'}
                {r.rechnungsdatum && <span className="text-gray-400"> — {formatDatum(r.rechnungsdatum)}</span>}
                {r.betrag_brutto && <span className="text-gray-400"> — {formatGeld(r.betrag_brutto)}</span>}
              </span>
              <button
                className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                disabled={rechnungLoesenMutation.isPending}
                onClick={() => rechnungLoesenMutation.mutate(r.id)}
              >
                Zuordnung lösen
              </button>
            </li>
          ))}
          {auftrag.rechnungen.length === 0 && (
            <li className="py-2 text-sm text-gray-400">Noch keine Rechnung zugeordnet.</li>
          )}
        </ul>
        <div className="flex items-center gap-2">
          <select
            className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
            value={rechnungAuswahl}
            onChange={e => setRechnungAuswahl(e.target.value)}
          >
            <option value="">Rechnung wählen…</option>
            {auswaehlbareRechnungen.map(r => (
              <option key={r.id} value={r.id}>
                {r.rechnungsnummer || r.dateiname} — {r.betrag_brutto ? formatGeld(r.betrag_brutto) : '–'}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            disabled={!rechnungAuswahl || rechnungZuordnenMutation.isPending}
            onClick={() => rechnungZuordnenMutation.mutate(rechnungAuswahl)}
          >
            Zuordnen
          </Button>
        </div>
        {auswaehlbareRechnungen.length === 0 && (
          <p className="text-xs text-gray-400 mt-2">Keine (weiteren) Rechnungen dieses Kreditors verfügbar.</p>
        )}
        {(rechnungZuordnenMutation.isError || rechnungLoesenMutation.isError) && (
          <p className="text-red-600 text-sm mt-2">
            {fehlerText(rechnungZuordnenMutation.error ?? rechnungLoesenMutation.error, 'Zuordnung fehlgeschlagen.')}
          </p>
        )}
      </div>

      {/* Kommentar */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Kommentar hinzufügen</h2>
        <textarea
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-20 resize-none"
          value={kommentarText}
          onChange={e => setKommentarText(e.target.value)}
        />
        <div className="mt-2">
          <Button
            size="sm"
            disabled={!kommentarText.trim() || kommentarMutation.isPending}
            onClick={() => kommentarMutation.mutate(kommentarText)}
          >
            Kommentar speichern
          </Button>
        </div>
      </div>

      {/* Verlauf */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-medium text-gray-800 mb-3">Verlauf</h2>
        <ul className="space-y-3">
          {auftrag.ereignisse.map(e => (
            <li
              key={e.id}
              className={`text-sm border-l-2 pl-3 ${e.typ === 'versand_fehlgeschlagen' ? 'border-red-400' : 'border-gray-200'}`}
            >
              <div className="flex items-center gap-2">
                <span className={`font-medium ${e.typ === 'versand_fehlgeschlagen' ? 'text-red-700' : 'text-gray-700'}`}>
                  {HWA_EREIGNIS_LABEL[e.typ] ?? e.typ}
                </span>
                <span className="text-gray-400 text-xs">{formatDatumZeit(e.erstellt_am)}</span>
                {e.erstellt_von_name && <span className="text-gray-400 text-xs">— {e.erstellt_von_name}</span>}
                {!e.erstellt_von_name && <span className="text-gray-400 text-xs">— System</span>}
              </div>
              {e.typ === 'versand_fehlgeschlagen' && (
                <p className="text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1 mt-1 text-xs">
                  Die Auftragsmail konnte nicht versendet werden{e.text ? `: ${e.text}` : '.'}
                </p>
              )}
              {e.typ !== 'versand_fehlgeschlagen' && e.text && (
                <p className="text-gray-600 mt-0.5">{e.text}</p>
              )}
              {(e.alter_wert || e.neuer_wert) && (
                <p className="text-gray-400 text-xs mt-0.5">{e.alter_wert ?? '–'} → {e.neuer_wert ?? '–'}</p>
              )}
            </li>
          ))}
          {auftrag.ereignisse.length === 0 && (
            <li className="text-sm text-gray-400">Noch keine Ereignisse.</li>
          )}
        </ul>
      </div>
    </div>
  )
}
