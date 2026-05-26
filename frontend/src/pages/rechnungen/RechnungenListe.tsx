import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rechnungenApi } from '../../api/rechnungen'
import { objekteApi } from '../../api/objekte'
import { wkzApi } from '../../api/wkz'
import { useObjektStore } from '../../stores/objekt'
import { Button } from '../../components/ui/Button'
import client from '../../api/client'
import type { RechnungList, RechnungStatus, Konto, Bankkonto, Kreditor } from '../../types'

const EUR = (v: string | number | null) =>
  v == null ? '—' : Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
const DATUM = (s: string | null) => s ? new Date(s).toLocaleDateString('de-DE') : '—'

const STATUS_STYLE: Record<string, string> = {
  importiert:     'bg-blue-100 text-blue-700',
  duplikat:       'bg-orange-100 text-orange-700',
  prueffall:      'bg-yellow-100 text-yellow-700',
  erkannt:        'bg-sky-100 text-sky-700',
  pruefung_match: 'bg-yellow-100 text-yellow-800',
  nicht_erkannt:  'bg-red-100 text-red-700',
  erfasst:        'bg-gray-100 text-gray-600',
  in_pruefung:    'bg-purple-100 text-purple-700',
  freigegeben:    'bg-green-100 text-green-700',
  gebucht:        'bg-green-200 text-green-800',
  bezahlt:        'bg-teal-100 text-teal-700',
  abgelehnt:      'bg-red-100 text-red-600',
  fehler:         'bg-red-200 text-red-800',
}

const STATUS_LABEL: Record<string, string> = {
  importiert:     'Importiert',
  duplikat:       'Duplikat',
  prueffall:      'Prüffall (alt)',
  erkannt:        'Erkannt (Stufe 1)',
  pruefung_match: 'Prüffall (Stufe 2)',
  nicht_erkannt:  'Nicht erkannt (Stufe 3)',
  erfasst:        'Erfasst',
  in_pruefung:    'In Prüfung',
  freigegeben:    'Freigegeben',
  gebucht:        'Gebucht',
  bezahlt:        'Bezahlt',
  abgelehnt:      'Abgelehnt',
  fehler:         'Fehler',
}

const PRUEFFALL_STATI = new Set(['pruefung_match', 'nicht_erkannt', 'in_pruefung'])

// ---------------------------------------------------------------------------
// Sachkonto erfassen (kein Buchungssatz — Buchung erfolgt erst bei Zahlung)
// ---------------------------------------------------------------------------
function SachkontoForm({ rechnung, onSuccess }: { rechnung: RechnungList; onSuccess: () => void }) {
  const qc = useQueryClient()
  const [objektId, setObjektId] = useState(rechnung.objekt_id ?? '')
  const [kontoId, setKontoId] = useState(rechnung.aufwandskonto_id ?? rechnung.kostenstelle_id ?? rechnung.vorgeschlagenes_konto_id ?? '')

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: () => objekteApi.list() })
  const { data: konten } = useQuery({
    queryKey: ['konten', objektId],
    queryFn: () => client.get<Konto[]>('/konten/', { params: { objekt: objektId, direktes_buchen: 'true' } }).then(r => r.data),
    enabled: !!objektId,
  })

  const mut = useMutation({
    mutationFn: () => rechnungenApi.buchen(rechnung.id, { objekt_id: objektId, konto_id: kontoId }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); onSuccess() },
  })

  const gewKonto = konten?.find(k => k.id === kontoId)

  return (
    <div className="border-t pt-4 space-y-3">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Sachkonto erfassen</div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Objekt</label>
          <select value={objektId} onChange={e => { setObjektId(e.target.value); setKontoId('') }}
                  className="border rounded px-2 py-1.5 text-sm w-full">
            <option value="">— Objekt wählen —</option>
            {(objekte ?? []).map(o => <option key={o.id} value={o.id}>{o.bezeichnung}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Sachkonto (Aufwand)</label>
          <select value={kontoId} onChange={e => setKontoId(e.target.value)}
                  className="border rounded px-2 py-1.5 text-sm w-full" disabled={!objektId}>
            <option value="">— Konto wählen —</option>
            {(konten ?? []).filter(k => k.aktiv).map(k => (
              <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>
            ))}
          </select>
        </div>
      </div>

      {gewKonto && rechnung.betrag_brutto && (
        <div className="bg-amber-50 border border-amber-200 rounded px-3 py-2 text-xs text-amber-800 font-mono">
          Sachkonto: {gewKonto.kontonummer} {gewKonto.kontoname} &nbsp;|&nbsp; {EUR(rechnung.betrag_brutto)} (Buchung bei Zahlung)
        </div>
      )}

      {mut.isError && <div className="text-xs text-red-600">Fehler. Bitte prüfen.</div>}

      <Button onClick={() => mut.mutate()} disabled={!objektId || !kontoId || mut.isPending}>
        {mut.isPending ? 'Speichere…' : 'Sachkonto speichern'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Phase 3 – Bankabgang (13600 / Bank)
// ---------------------------------------------------------------------------
function BankabgangForm({ rechnung, onSuccess }: { rechnung: RechnungList; onSuccess: () => void }) {
  const qc = useQueryClient()
  const [habenKontoId, setHabenKontoId] = useState('')
  const [buchungsdatum, setBuchungsdatum] = useState(new Date().toISOString().slice(0, 10))

  // Buchungskonten 18xxx aus dem Kontenplan
  const { data: konten } = useQuery({
    queryKey: ['konten-bank', rechnung.objekt_id],
    queryFn: () => client.get<Konto[]>('/konten/', { params: { objekt: rechnung.objekt_id } }).then(r => r.data),
    enabled: !!rechnung.objekt_id,
  })
  const bankKonten = (konten ?? []).filter(k => k.aktiv && k.kontonummer.startsWith('18'))

  // Zahlungsverkehr-Bankkonto des Objekts
  const { data: bankkontenMaster } = useQuery({
    queryKey: ['bankkonten', rechnung.objekt_id],
    queryFn: () => client.get<Bankkonto[]>('/bankkonten/', { params: { objekt: rechnung.objekt_id } }).then(r => r.data),
    enabled: !!rechnung.objekt_id,
  })
  const zvBankkonto = (bankkontenMaster ?? []).find(b => b.zahlungsverkehr && b.aktiv)
  const zvKontonummer = zvBankkonto
    ? zvBankkonto.konto_typ === 'bewirtschaftung'
      ? '18000'
      : zvBankkonto.reihenfolge === 1 ? '18911' : `0991${zvBankkonto.reihenfolge}`
    : null

  // Auto-Vorauswahl wenn Zahlungsverkehrskonto gesetzt
  useEffect(() => {
    if (zvKontonummer && bankKonten.length > 0 && !habenKontoId) {
      const match = bankKonten.find(k => k.kontonummer === zvKontonummer)
      if (match) setHabenKontoId(match.id)
    }
  }, [zvKontonummer, bankKonten.length])

  const zvKonto = habenKontoId ? bankKonten.find(k => k.id === habenKontoId) : null

  const mut = useMutation({
    mutationFn: () => rechnungenApi.bankabgang(rechnung.id, { haben_konto_id: habenKontoId, buchungsdatum }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); onSuccess() },
  })

  return (
    <div className="border-t pt-4 space-y-3">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Bankabgang erfassen</div>

      <div className="bg-teal-50 border border-teal-200 rounded px-3 py-2 text-xs text-teal-800 font-mono">
        13600 / Bankkonto &nbsp;|&nbsp; {EUR(rechnung.betrag_brutto)}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Bankkonto (Haben)</label>
          {zvBankkonto && zvKonto ? (
            <div className="border rounded px-2 py-1.5 text-sm bg-gray-50 text-gray-800">
              {zvKonto.kontonummer} — {zvKonto.kontoname}
              <span className="ml-2 text-xs text-teal-600">({zvBankkonto.bezeichnung})</span>
            </div>
          ) : (
            <select value={habenKontoId} onChange={e => setHabenKontoId(e.target.value)}
                    className="border rounded px-2 py-1.5 text-sm w-full">
              <option value="">— Konto wählen —</option>
              {bankKonten.map(k => <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>)}
            </select>
          )}
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Buchungsdatum</label>
          <input type="date" value={buchungsdatum} onChange={e => setBuchungsdatum(e.target.value)}
                 className="border rounded px-2 py-1.5 text-sm w-full" />
        </div>
      </div>

      {mut.isError && <div className="text-xs text-red-600">Fehler beim Buchen. Bitte prüfen.</div>}

      <Button onClick={() => mut.mutate()} disabled={!habenKontoId || mut.isPending}>
        {mut.isPending ? 'Wird gebucht…' : 'Bankabgang buchen'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Detail-Modal
// ---------------------------------------------------------------------------
function SepaToggle({ rechnung }: { rechnung: RechnungList }) {
  const qc = useQueryClient()
  const mut = useMutation({
    mutationFn: (val: boolean) => rechnungenApi.update(rechnung.id, { sepa_lastschrift: val } as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rechnungen'] }),
  })
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={rechnung.sepa_lastschrift}
        onChange={e => mut.mutate(e.target.checked)}
        disabled={mut.isPending}
        className="w-4 h-4 accent-blue-600"
      />
      <span className="text-sm text-gray-700">SEPA-Lastschrift</span>
      {mut.isPending && <span className="text-xs text-gray-400">…</span>}
    </label>
  )
}

function DetailModal({ rechnung, onClose }: { rechnung: RechnungList; onClose: () => void }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [begruendung, setBegruendung] = useState('')

  // Editierbare Felder
  const [editKreditorId, setEditKreditorId]               = useState('')
  const [editRechnungsnummer, setEditRechnungsnummer]     = useState(rechnung.rechnungsnummer ?? '')
  const [editRechnungsdatum, setEditRechnungsdatum]       = useState(rechnung.rechnungsdatum ?? '')
  const [editFaelligkeitsdatum, setEditFaelligkeitsdatum] = useState(rechnung.faelligkeitsdatum ?? '')
  const [editBetragBrutto, setEditBetragBrutto]           = useState(rechnung.betrag_brutto ?? '')
  const [editObjektId, setEditObjektId]                   = useState(rechnung.objekt_id ?? '')

  const { data: detail } = useQuery({
    queryKey: ['rechnung', rechnung.id],
    queryFn: () => rechnungenApi.get(rechnung.id),
  })

  // Kreditor-UUID erst nach Laden von detail verfügbar
  useEffect(() => {
    if (detail?.kreditor && !editKreditorId) setEditKreditorId(detail.kreditor)
  }, [detail?.kreditor])

  const { data: kreditoren } = useQuery<Kreditor[]>({
    queryKey: ['kreditoren'],
    queryFn: () => rechnungenApi.kreditoren({ aktiv: 'true' }),
  })
  const { data: objekte } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
  })

  // WKZ-Vorlagen die zu dieser Rechnung verknüpft sind (für Button-Label)
  const { data: linkedWkz } = useQuery({
    queryKey: ['wkz-vorlagen-rechnung', rechnung.id],
    queryFn: () => wkzApi.vorlagenJeRechnung(rechnung.id),
    staleTime: 30_000,
  })
  const wkzAnzahl = linkedWkz?.length ?? 0

  function handleWkzButton() {
    const params = new URLSearchParams()
    params.set('rechnung_id', rechnung.id)
    if (detail?.kreditor)        params.set('kreditor_id', detail.kreditor)
    if (rechnung.objekt_id)      params.set('objekt_id', rechnung.objekt_id)
    if (rechnung.betrag_brutto)  params.set('betrag', String(rechnung.betrag_brutto))
    if (rechnung.rechnungsnummer) params.set('bezeichnung', rechnung.rechnungsnummer)
    onClose()
    navigate(`/buchhaltung/wkz-vorlagen/neu?${params.toString()}`)
  }

  const mutKorrektur = useMutation({
    mutationFn: () => rechnungenApi.update(rechnung.id, {
      kreditor:          editKreditorId || null,
      rechnungsnummer:   editRechnungsnummer,
      rechnungsdatum:    editRechnungsdatum    || null,
      faelligkeitsdatum: editFaelligkeitsdatum || null,
      betrag_brutto:     editBetragBrutto
        ? parseFloat(editBetragBrutto.replace(',', '.'))
        : null,
      objekt: editObjektId || null,
    } as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rechnungen'] }),
  })

  const korrDirty = (
    editKreditorId      !== (detail?.kreditor        ?? '') ||
    editRechnungsnummer !== (rechnung.rechnungsnummer ?? '') ||
    editRechnungsdatum  !== (rechnung.rechnungsdatum  ?? '') ||
    editFaelligkeitsdatum !== (rechnung.faelligkeitsdatum ?? '') ||
    editBetragBrutto    !== (rechnung.betrag_brutto   ?? '') ||
    editObjektId        !== (rechnung.objekt_id       ?? '')
  )

  const freigebenMut = useMutation({
    mutationFn: () => rechnungenApi.freigeben(rechnung.id, begruendung ? { begruendung } : undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); onClose() },
  })
  const ablehnMut = useMutation({
    mutationFn: () => rechnungenApi.ablehnen(rechnung.id, begruendung),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); onClose() },
  })
  const alsNeuMut = useMutation({
    mutationFn: () => rechnungenApi.alsNeu(rechnung.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); onClose() },
  })

  const kannFreigeben = ['importiert', 'prueffall', 'in_pruefung', 'erfasst'].includes(rechnung.status)
  const kannAblehnen = !['bezahlt', 'abgelehnt'].includes(rechnung.status)
  const kannAlsNeu = ['prueffall', 'duplikat'].includes(rechnung.status)
  const kannSachkonto = !['bezahlt', 'abgelehnt', 'fehler'].includes(rechnung.status)
  const kannBankabgang = rechnung.status === 'bezahlt'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b flex justify-between items-start">
          <div>
            <h2 className="text-lg font-bold text-gray-900">
              {rechnung.dateiname || rechnung.rechnungsnummer || 'Rechnung'}
            </h2>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLE[rechnung.status] ?? 'bg-gray-100'}`}>
              {rechnung.status}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">

          {/* ── Editierbare Rechnungsfelder ── */}
          <div className="space-y-2 text-sm">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2">
              Rechnungsdetails
              {korrDirty && <span className="text-orange-500 font-normal normal-case">● ungespeichert</span>}
            </div>

            {/* Lieferant — Kreditor-Dropdown */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500 w-36 shrink-0">Lieferant</span>
              <select
                value={editKreditorId}
                onChange={e => setEditKreditorId(e.target.value)}
                className="border rounded px-2 py-1 text-sm flex-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="">— Kreditor wählen —</option>
                {(kreditoren ?? []).map(k => (
                  <option key={k.id} value={k.id}>
                    {k.kreditorennummer ? `[${k.kreditorennummer}] ` : ''}{k.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Rechnungsnummer */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500 w-36 shrink-0">Rechnungsnr.</span>
              <input type="text" value={editRechnungsnummer}
                onChange={e => setEditRechnungsnummer(e.target.value)}
                className="border rounded px-2 py-1 text-sm flex-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400" />
            </div>

            {/* Rechnungsdatum */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500 w-36 shrink-0">Rechnungsdatum</span>
              <input type="date" value={editRechnungsdatum}
                onChange={e => setEditRechnungsdatum(e.target.value)}
                className="border rounded px-2 py-1 text-sm flex-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400" />
            </div>

            {/* Fällig am */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500 w-36 shrink-0">Fällig am</span>
              <input type="date" value={editFaelligkeitsdatum}
                onChange={e => setEditFaelligkeitsdatum(e.target.value)}
                className="border rounded px-2 py-1 text-sm flex-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400" />
            </div>

            {/* Betrag brutto */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500 w-36 shrink-0">Betrag brutto</span>
              <input type="number" step="0.01" value={editBetragBrutto}
                onChange={e => setEditBetragBrutto(e.target.value)}
                className="border rounded px-2 py-1 text-sm flex-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400" />
            </div>

            {/* Objekt */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500 w-36 shrink-0">Objekt</span>
              <select
                value={editObjektId}
                onChange={e => setEditObjektId(e.target.value)}
                className="border rounded px-2 py-1 text-sm flex-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="">— Objekt wählen —</option>
                {(objekte ?? []).map((o: { id: string; bezeichnung: string }) => (
                  <option key={o.id} value={o.id}>{o.bezeichnung}</option>
                ))}
              </select>
            </div>

            {/* Weitere read-only Infos */}
            <div className="grid grid-cols-2 gap-2 pt-1">
              {[
                ['Sachkonto', rechnung.kostenstelle_label || rechnung.aufwandskonto_label || (rechnung.vorgeschlagenes_konto_label ? rechnung.vorgeschlagenes_konto_label + ' (Vorschlag)' : '—')],
                ['MwSt.', detail?.mwst_satz ? `${detail.mwst_satz} %` : '—'],
              ].map(([label, value]) => (
                <div key={label} className="bg-gray-50 rounded px-3 py-2">
                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">{label}</div>
                  <div className="font-medium text-gray-800 text-sm">{value}</div>
                </div>
              ))}
            </div>

            {/* Speichern-Button */}
            {korrDirty && (
              <div className="flex items-center gap-3 pt-1">
                <Button onClick={() => mutKorrektur.mutate()} disabled={mutKorrektur.isPending}>
                  {mutKorrektur.isPending ? 'Speichert…' : 'Korrekturen speichern'}
                </Button>
                {mutKorrektur.isSuccess && <span className="text-green-600 text-xs">✓ Gespeichert</span>}
                {mutKorrektur.isError   && <span className="text-red-600 text-xs">Fehler beim Speichern</span>}
              </div>
            )}
          </div>

          <div className="flex items-center gap-3 px-1">
            <SepaToggle rechnung={rechnung} />
          </div>

          {rechnung.duplikat_typ && (
            <div className="bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-sm">
              <div className="font-semibold text-orange-700 mb-1">
                {rechnung.status === 'duplikat' ? 'Duplikat erkannt' : 'Prüffall'}
                {` (${rechnung.duplikat_typ})`}
              </div>
              {rechnung.duplikat_von_dateiname && (
                <div className="text-orange-600">Vorlage: {rechnung.duplikat_von_dateiname}</div>
              )}
            </div>
          )}

          {detail?.verarbeitungsnotiz && (
            <div className="text-xs text-gray-400 bg-gray-50 rounded p-3">
              {detail.verarbeitungsnotiz}
            </div>
          )}

          {(detail?.pfad || detail?.pdf_upload) && (
            <button
              onClick={() => rechnungenApi.openPdf(rechnung.id).catch(() => alert('PDF konnte nicht geladen werden.'))}
              className="text-sm text-blue-600 hover:underline text-left"
            >
              PDF öffnen →
            </button>
          )}

          {/* WKZ-Button */}
          <div className="border rounded-lg px-4 py-3 bg-gray-50">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Wiederkehrende Zahlung
            </div>
            {wkzAnzahl > 0 && (
              <p className="text-xs text-gray-500 mb-2">
                Bereits {wkzAnzahl} WKZ-Vorlage{wkzAnzahl > 1 ? 'n' : ''} mit dieser Rechnung verknüpft.
              </p>
            )}
            <Button variant="secondary" onClick={handleWkzButton}>
              {wkzAnzahl === 0
                ? '↻ WKZ aus diesem Beleg anlegen'
                : '↻ Zusätzlich WKZ aus diesem Beleg anlegen'}
            </Button>
          </div>

          {kannSachkonto && (
            <SachkontoForm rechnung={rechnung} onSuccess={onClose} />
          )}

          {kannBankabgang && (
            <BankabgangForm rechnung={rechnung} onSuccess={onClose} />
          )}

          {(kannFreigeben || kannAblehnen || kannAlsNeu) && (
            <div className="border-t pt-4 space-y-3">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Prüfung</div>
              <textarea
                value={begruendung}
                onChange={e => setBegruendung(e.target.value)}
                rows={2}
                placeholder="Begründung (optional bei Freigabe, Pflicht bei Ablehnung)"
                className="border rounded-lg px-3 py-2 text-sm w-full resize-none"
              />
              <div className="flex gap-2 flex-wrap">
                {kannAlsNeu && (
                  <Button variant="secondary" onClick={() => alsNeuMut.mutate()} disabled={alsNeuMut.isPending}>
                    Als neue Rechnung bestätigen
                  </Button>
                )}
                {kannFreigeben && (
                  <Button onClick={() => freigebenMut.mutate()} disabled={freigebenMut.isPending}>
                    Freigeben
                  </Button>
                )}
                {kannAblehnen && (
                  <Button variant="secondary" onClick={() => ablehnMut.mutate()}
                          disabled={ablehnMut.isPending || !begruendung}>
                    Ablehnen
                  </Button>
                )}
              </div>
            </div>
          )}

          {(detail?.freigaben ?? []).length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Freigabe-Historie
              </div>
              <div className="space-y-1.5">
                {detail!.freigaben.map(f => (
                  <div key={f.id}
                       className="flex items-center gap-3 text-xs text-gray-600 bg-gray-50 rounded px-3 py-1.5">
                    <span className={`px-1.5 py-0.5 rounded font-medium ${
                      f.entscheidung === 'freigegeben' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'
                    }`}>
                      {f.entscheidung}
                    </span>
                    <span>{f.bearbeiter_name}</span>
                    <span className="text-gray-400">{new Date(f.zeitstempel).toLocaleString('de-DE')}</span>
                    {f.begruendung && <span className="text-gray-500">— {f.begruendung}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptseite
// ---------------------------------------------------------------------------

const ALLE_STATUS: RechnungStatus[] = [
  'importiert', 'duplikat', 'erfasst', 'in_pruefung', 'freigegeben', 'gebucht', 'bezahlt', 'abgelehnt', 'fehler',
]

export function RechnungenListe() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const objektId = useObjektStore(s => s.selectedId)
  const [statusFilter, setStatusFilter] = useState('')
  const [suche, setSuche] = useState('')
  const [selected, setSelected] = useState<RechnungList | null>(null)

  const handleRowClick = (r: RechnungList) => {
    if (PRUEFFALL_STATI.has(r.status)) {
      navigate(`/rechnungen/${r.id}/prueffall`)
    } else {
      setSelected(r)
    }
  }

  const { data: ocrCount, refetch: refetchOcrCount } = useQuery({
    queryKey: ['ocr-wiederholen-count'],
    queryFn: rechnungenApi.ocrWiederholenAnzahl,
  })
  const [ocrErgebnis, setOcrErgebnis] = useState<{ verarbeitet: number; fehler: number; noch_unvollstaendig: number } | null>(null)
  const ocrMut = useMutation({
    mutationFn: rechnungenApi.ocrWiederholen,
    onSuccess: (data) => {
      setOcrErgebnis(data)
      refetchOcrCount()
      qc.invalidateQueries({ queryKey: ['rechnungen'] })
    },
  })

  const { data: rechnungen, isLoading } = useQuery({
    queryKey: ['rechnungen', objektId, statusFilter, suche],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektId) params.objekt = objektId
      if (statusFilter === '__prueffall_alle__') {
        params.status = 'prueffall,pruefung_match,nicht_erkannt'
      } else if (statusFilter) {
        params.status = statusFilter
      }
      if (suche) params.search = suche
      return rechnungenApi.list(params)
    },
  })

  const offen = (rechnungen ?? []).filter(r =>
    ['importiert', 'prueffall', 'duplikat', 'in_pruefung', 'erfasst', 'pruefung_match', 'nicht_erkannt'].includes(r.status)
  ).length

  return (
    <div>
      {selected && <DetailModal rechnung={selected} onClose={() => setSelected(null)} />}

      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Rechnungseingang</h1>
          {offen > 0 && (
            <p className="text-sm text-orange-600 font-medium mt-0.5">
              {offen} Rechnung(en) warten auf Bearbeitung
            </p>
          )}
        </div>
        {(ocrCount?.anzahl ?? 0) > 0 && (
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => { setOcrErgebnis(null); ocrMut.mutate() }}
              disabled={ocrMut.isPending}
            >
              {ocrMut.isPending
                ? 'OCR läuft…'
                : `OCR wiederholen (${ocrCount!.anzahl})`}
            </Button>
          </div>
        )}
      </div>

      {ocrErgebnis && (
        <div className="mb-4 bg-green-50 border border-green-200 rounded p-3 text-sm text-green-800 flex items-center justify-between">
          <span>
            OCR abgeschlossen: <strong>{ocrErgebnis.verarbeitet}</strong> erkannt
            {ocrErgebnis.noch_unvollstaendig > 0 && `, ${ocrErgebnis.noch_unvollstaendig} noch unvollständig`}
            {ocrErgebnis.fehler > 0 && `, ${ocrErgebnis.fehler} Fehler`}
          </span>
          <button className="text-green-600 underline text-xs ml-3" onClick={() => setOcrErgebnis(null)}>Schließen</button>
        </div>
      )}

      <div className="flex gap-3 mb-4 flex-wrap">
        <input
          type="text"
          placeholder="Suche Datei, Lieferant, Nr…"
          value={suche}
          onChange={e => setSuche(e.target.value)}
          className="border rounded px-3 py-2 text-sm w-64"
        />
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="border rounded px-3 py-2 text-sm"
        >
          <option value="">Alle Status</option>
          <option value="__prueffall_alle__">— Alle Prüffälle —</option>
          {ALLE_STATUS.map(s => (
            <option key={s} value={s}>{STATUS_LABEL[s] ?? s}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Lade Rechnungen…</div>
      ) : (
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Lieferant / Datei</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Nr.</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium w-28">Datum</th>
                <th className="text-right px-4 py-3 text-gray-500 font-medium w-32">Betrag</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Objekt</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Sachkonto</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium w-32">Status</th>
                <th className="px-4 py-3 w-8" />
              </tr>
            </thead>
            <tbody>
              {(rechnungen ?? []).length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-10 text-gray-400">
                    Keine Rechnungen vorhanden
                  </td>
                </tr>
              ) : (rechnungen ?? []).map(r => (
                <tr key={r.id} onClick={() => handleRowClick(r)}
                    className="border-t hover:bg-gray-50 cursor-pointer">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-800 truncate max-w-[180px]">
                      {r.kreditor_name || r.lieferant_name || '—'}
                    </div>
                    <div className="text-xs text-gray-400 truncate max-w-[180px]">{r.dateiname}</div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">{r.rechnungsnummer || '—'}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{DATUM(r.rechnungsdatum)}</td>
                  <td className="px-4 py-3 text-right font-semibold tabular-nums">{EUR(r.betrag_brutto)}</td>
                  <td className="px-4 py-3">
                    {r.objekt_bezeichnung
                      ? <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-medium">{r.objekt_bezeichnung}</span>
                      : <span className="text-xs text-gray-300">—</span>
                    }
                  </td>
                  <td className="px-4 py-3">
                    {r.aufwandskonto_label || r.kostenstelle_label
                      ? <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded font-mono">{r.aufwandskonto_label || r.kostenstelle_label}</span>
                      : r.vorgeschlagenes_konto_label
                      ? <span className="text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded font-mono">{r.vorgeschlagenes_konto_label} *</span>
                      : <span className="text-xs text-gray-300">—</span>
                    }
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLE[r.status] ?? 'bg-gray-100'}`}>
                      {STATUS_LABEL[r.status] ?? r.status}
                    </span>
                    {r.op_nummer && (
                      <div className="text-xs text-gray-500 font-mono mt-0.5">OP-{r.op_nummer}</div>
                    )}
                    {r.duplikat_typ && (
                      <div className="text-xs text-orange-400 mt-0.5">{r.duplikat_typ}</div>
                    )}
                    {r.zugewiesen_an_name && PRUEFFALL_STATI.has(r.status) && (
                      <div className="text-xs text-gray-400 mt-0.5">→ {r.zugewiesen_an_name}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-300 text-lg">›</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
