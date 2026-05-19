import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rechnungenApi } from '../../api/rechnungen'
import { objekteApi } from '../../api/objekte'
import { wirtschaftsjahreApi } from '../../api/wirtschaftsjahre'
import client from '../../api/client'
import { Button } from '../../components/ui/Button'
import type { Rechnung, Kreditor, Konto, DublettKandidat, Wirtschaftsjahr } from '../../types'

const EUR = (v: string | number | null) =>
  v == null ? '—' : Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

const KONFIDENZ_FARBE = (k: number) =>
  k >= 0.9 ? 'text-green-600' : k >= 0.7 ? 'text-yellow-600' : 'text-red-500'

export default function PrueffallDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: rechnung, isLoading } = useQuery<Rechnung>({
    queryKey: ['rechnung', id],
    queryFn: () => rechnungenApi.get(id!),
    enabled: !!id,
  })

  const [kreditorId, setKreditorId]                   = useState('')
  const [objektId, setObjektId]                       = useState('')
  const [wirtschaftsjahrId, setWirtschaftsjahrId]     = useState('')
  const [aufwandskontoId, setAufwandskontoId]         = useState('')
  const [aufwandskontoAendern, setAufwandskontoAendern] = useState(false)
  const [lernen, setLernen]                           = useState(true)
  const [sepaLastschrift, setSepaLastschrift]         = useState(false)

  // Stufe 3: neuer Kreditor-Workflow
  const [zeigeNeuForm, setZeigeNeuForm] = useState(false)
  const [neuName, setNeuName]           = useState('')
  const [neuIban, setNeuIban]           = useState('')
  const [dubWarn, setDubWarn]           = useState<DublettKandidat[]>([])

  useEffect(() => {
    if (!rechnung) return
    setKreditorId(prev => prev || rechnung.kreditor || '')
    setObjektId(prev => prev || rechnung.objekt || '')
    setAufwandskontoId(prev => prev || rechnung.aufwandskonto_id || '')
    setSepaLastschrift(rechnung.sepa_lastschrift ?? false)
    if (rechnung.erkennungs_stufe === '3') {
      setNeuName(prev => prev || rechnung.lieferant_name || '')
      setNeuIban(prev => prev || rechnung.lieferant_iban || '')
    }
  }, [rechnung?.id])

  const { data: kreditoren } = useQuery<Kreditor[]>({
    queryKey: ['kreditoren'],
    queryFn: () => rechnungenApi.kreditoren({ aktiv: 'true' }),
  })
  const { data: objekte } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
  })
  const effektivObjektId = objektId || rechnung?.objekt

  const { data: wirtschaftsjahre } = useQuery<Wirtschaftsjahr[]>({
    queryKey: ['wirtschaftsjahre', effektivObjektId],
    queryFn: () => wirtschaftsjahreApi.list({ objekt: effektivObjektId! }),
    enabled: !!effektivObjektId,
  })

  // Neuestes WJ vorauswählen (sobald Liste geladen)
  useEffect(() => {
    if (!wirtschaftsjahre?.length || wirtschaftsjahrId) return
    const latest = [...wirtschaftsjahre].sort((a, b) => b.jahr - a.jahr)[0]
    setWirtschaftsjahrId(latest.id)
  }, [wirtschaftsjahre])

  const { data: konten } = useQuery<Konto[]>({
    queryKey: ['konten-alle', wirtschaftsjahrId, effektivObjektId],
    queryFn: () => {
      const params = wirtschaftsjahrId
        ? { wirtschaftsjahr: wirtschaftsjahrId }
        : { objekt: effektivObjektId }
      return client.get<Konto[]>('/konten/', { params }).then(r => r.data)
    },
    enabled: !!(wirtschaftsjahrId || effektivObjektId),
  })

  // Duplikat-Prüfung bei Stufe 3
  const { data: duplikatResult } = useQuery({
    queryKey: ['duplikat-pruefen', rechnung?.id],
    queryFn: () => rechnungenApi.duplikatPruefen(rechnung!.lieferant_name!),
    enabled: rechnung?.erkennungs_stufe === '3' && !!rechnung?.lieferant_name,
    staleTime: Infinity,
  })
  const duplikatKandidaten = duplikatResult?.kandidaten ?? []

  // Aufwandskonten: 50000–55999 ohne direktes_buchen
  const aufwandskonten = (konten ?? []).filter(k =>
    k.aktiv && k.kontoart === 'standard' && !k.direktes_buchen &&
    k.kontonummer >= '50000' && k.kontonummer <= '55999'
  )

  // Identifikations-Mutationen (für pruefung_match / nicht_erkannt)
  const mutSpeichern = useMutation({
    mutationFn: () => rechnungenApi.identifizieren(id!, {
      kreditor_id:      kreditorId || rechnung?.kreditor || '',
      objekt_id:        objektId   || rechnung?.objekt   || '',
      aufwandskonto_id: aufwandskontoId || rechnung?.aufwandskonto_id || undefined,
      modus: 'speichern',
      lernen,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); navigate(-1) },
  })

  const mutDirektfreigeben = useMutation({
    mutationFn: () => rechnungenApi.identifizieren(id!, {
      kreditor_id:      kreditorId || rechnung?.kreditor || '',
      objekt_id:        objektId   || rechnung?.objekt   || '',
      aufwandskonto_id: aufwandskontoId || rechnung?.aufwandskonto_id || undefined,
      modus: 'freigeben',
      lernen,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); navigate(-1) },
  })

  // Freigabe-Mutation (für in_pruefung — ruft /freigeben/ auf)
  const mutFreigabeGenehmigen = useMutation({
    mutationFn: () => rechnungenApi.freigeben(id!, {
      aufwandskonto_id: aufwandskontoAendern
        ? (aufwandskontoId || undefined)
        : undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); navigate(-1) },
  })

  const mutAblehnen = useMutation({
    mutationFn: () => rechnungenApi.ablehnen(id!, begruendung),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rechnungen'] }); navigate(-1) },
  })

  const mutNeuerKreditor = useMutation({
    mutationFn: (data: { name: string; iban?: string }) => rechnungenApi.createKreditor(data),
    onSuccess: (k) => { setKreditorId(k.id); setZeigeNeuForm(false); setDubWarn([]) },
  })

  const mutSepa = useMutation({
    mutationFn: (val: boolean) => rechnungenApi.update(id!, { sepa_lastschrift: val } as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rechnung', id] }),
  })

  const handleNeuKreditorAnlegen = async () => {
    const name = neuName.trim()
    if (!name) return
    const iban = neuIban.replace(/\s/g, '').toUpperCase() || undefined
    const result = await rechnungenApi.duplikatPruefen(name, iban)
    const high = result.kandidaten.filter(k => k.score >= 0.70)
    if (high.length > 0) {
      setDubWarn(high)
      return
    }
    mutNeuerKreditor.mutate({ name, iban })
  }

  const [begruendung, setBegruendung] = useState('')

  if (isLoading || !rechnung) {
    return <div className="p-6 text-gray-500">Lade…</div>
  }

  const istFreigabeModus = rechnung.status === 'in_pruefung'

  const kannSpeichern = !!(
    (kreditorId || rechnung.kreditor) &&
    (objektId   || rechnung.objekt)
  )
  const kannDirektfreigeben = kannSpeichern && rechnung.darf_direkt_freigeben

  // Für Freigabe-Modus: Aufwandskonto muss gesetzt sein (entweder vorhandenes oder neues)
  const effektivesAufwandskontoId = aufwandskontoAendern
    ? aufwandskontoId
    : (rechnung.aufwandskonto_id || aufwandskontoId)
  const kannFreigeben = istFreigabeModus && !!effektivesAufwandskontoId

  const konfidenz = rechnung.erkennungs_konfidenz

  const aufwandskontoErkannt = istFreigabeModus
    ? !!rechnung.aufwandskonto_id
    : !!(rechnung.aufwandskonto_id && (!konfidenz || konfidenz.aufwandskonto >= 1.0))

  const anyMutError = mutSpeichern.error || mutDirektfreigeben.error || mutFreigabeGenehmigen.error || mutAblehnen.error
  const mutErrorMsg = anyMutError
    ? ((anyMutError as { response?: { data?: { error?: string } } })?.response?.data?.error
        || (anyMutError as Error)?.message)
    : null

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      {/* Kontext-Banner */}
      {istFreigabeModus && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-200 px-4 py-2 text-sm text-indigo-800">
          <strong>Freigabe erforderlich</strong> — Betrag über automatischem Limit.
          Prüfen Sie das Sachkonto und geben Sie die Rechnung frei.
        </div>
      )}
      {!istFreigabeModus && rechnung.erkennungs_stufe === '2' && (
        <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-2 text-sm text-blue-800">
          Sie bearbeiten als <strong>Objektbetreuer</strong> von {rechnung.objekt_bezeichnung || 'diesem Objekt'}.
          Aufwandskonto und ggf. Kreditor bitte bestätigen.
        </div>
      )}
      {!istFreigabeModus && rechnung.erkennungs_stufe === '3' && (
        <div className="rounded-lg bg-orange-50 border border-orange-200 px-4 py-2 text-sm text-orange-800">
          <strong>Frontoffice-Aufgabe:</strong> Objekt und Kreditor vollständig zuordnen.
          Nach Identifikation läuft die Rechnung in den regulären Freigabe-Workflow.
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => navigate(-1)} className="text-sm text-blue-600 hover:underline mb-1">
            ← Zurück
          </button>
          <h1 className="text-xl font-semibold">
            {istFreigabeModus ? 'Freigabe — ' : 'Prüffall — '}
            {rechnung.dateiname || rechnung.rechnungsnummer || rechnung.id.slice(0, 8)}
          </h1>
          <div className="flex gap-2 mt-1">
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${
              istFreigabeModus ? 'bg-indigo-100 text-indigo-700' :
              rechnung.erkennungs_stufe === '2' ? 'bg-blue-100 text-blue-700' :
              'bg-red-100 text-red-700'
            }`}>
              {istFreigabeModus ? 'In Prüfung' :
               rechnung.erkennungs_stufe === '2' ? 'Stufe 2 — Objektbetreuer' :
               rechnung.erkennungs_stufe === '3' ? 'Stufe 3 — Nicht erkannt' : 'Prüffall'}
            </span>
            <span className="text-sm font-semibold text-gray-800">{EUR(rechnung.betrag_brutto)}</span>
          </div>
        </div>
        {(rechnung.pfad || rechnung.pdf_upload) && (
          <Button variant="secondary" onClick={() => rechnungenApi.openPdf(rechnung.id).catch(() => alert('PDF konnte nicht geladen werden.'))}>
            PDF ansehen
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Linke Spalte: Rechnungsdetails */}
        <div className="space-y-4">
          <div className="bg-gray-50 rounded-lg p-4 text-sm space-y-2">
            <div className="font-semibold text-gray-600 text-xs uppercase tracking-wide mb-2">Rechnungsdetails</div>
            <Row label="Lieferant (OCR)" value={rechnung.lieferant_name} />
            <Row label="Leistungstext"   value={rechnung.leistungstext || rechnung.leistungsbeschreibung} />
            <Row label="Betrag brutto"   value={EUR(rechnung.betrag_brutto)} />
            <Row label="Rechnungsdatum"  value={rechnung.rechnungsdatum ?? '—'} />
            <Row label="Dateiname"       value={rechnung.dateiname} />
            {istFreigabeModus && rechnung.zugewiesen_an_name && (
              <Row label="Zugewiesen an" value={rechnung.zugewiesen_an_name} />
            )}
          </div>

          {/* Erkennungs-Konfidenz */}
          {konfidenz && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm">
              <div className="font-semibold text-blue-700 text-xs uppercase tracking-wide mb-2">Erkennungs-Konfidenz</div>
              {(['kreditor', 'objekt', 'aufwandskonto'] as const).map(dim => (
                <div key={dim} className="flex justify-between py-0.5">
                  <span className="text-gray-600 capitalize">{dim}</span>
                  <span className={`font-mono font-medium ${KONFIDENZ_FARBE(konfidenz[dim])}`}>
                    {(konfidenz[dim] * 100).toFixed(0)} %
                    {konfidenz[dim] >= 0.9 ? ' ✓' : konfidenz[dim] > 0 ? ' ?' : ' —'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Rechte Spalte */}
        <div className="space-y-4">

          {/* ── FREIGABE-MODUS (in_pruefung) ── */}
          {istFreigabeModus ? (
            <>
              {/* Kreditor — nur anzeigen */}
              <DimensionCard
                titel="Kreditor"
                erkannt={!!rechnung.kreditor_name}
                erkannterWert={rechnung.kreditor_name}
              >
                {!rechnung.kreditor_name && (
                  <p className="text-xs text-gray-400">Kein Kreditor zugeordnet</p>
                )}
              </DimensionCard>

              {/* Objekt — nur anzeigen */}
              <DimensionCard
                titel="Objekt"
                erkannt={!!rechnung.objekt_bezeichnung}
                erkannterWert={rechnung.objekt_bezeichnung}
              >
                {!rechnung.objekt_bezeichnung && (
                  <p className="text-xs text-gray-400">Kein Objekt zugeordnet</p>
                )}
              </DimensionCard>

              {/* Aufwandskonto — mit "Sachkonto ändern"-Toggle */}
              <DimensionCard
                titel="Aufwandskonto"
                erkannt={aufwandskontoErkannt}
                erkannterWert={rechnung.aufwandskonto_label}
              >
                {aufwandskontoErkannt && !aufwandskontoAendern ? (
                  <button
                    type="button"
                    onClick={() => setAufwandskontoAendern(true)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Sachkonto ändern
                  </button>
                ) : (
                  <>
                    <WjSelektor
                      wirtschaftsjahre={wirtschaftsjahre}
                      wirtschaftsjahrId={wirtschaftsjahrId}
                      onChange={id => { setWirtschaftsjahrId(id); setAufwandskontoId('') }}
                    />
                    <select
                      value={aufwandskontoId}
                      onChange={e => setAufwandskontoId(e.target.value)}
                      className="border rounded px-2 py-1.5 text-sm w-full"
                    >
                      <option value="">— Aufwandskonto wählen (50xxx–55xxx) —</option>
                      {aufwandskonten.map(k => (
                        <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>
                      ))}
                    </select>
                    {aufwandskontoAendern && (
                      <button
                        type="button"
                        onClick={() => { setAufwandskontoAendern(false); setAufwandskontoId('') }}
                        className="text-xs text-gray-400 hover:underline mt-1"
                      >
                        Abbrechen
                      </button>
                    )}
                    {!aufwandskonten.length && (
                      <p className="text-xs text-gray-400 mt-1">Keine Aufwandskonten für dieses Objekt</p>
                    )}
                  </>
                )}
              </DimensionCard>

              {/* Fehleranzeige */}
              {mutErrorMsg && (
                <div className="rounded bg-red-50 border border-red-200 p-3">
                  <p className="text-sm text-red-700">{mutErrorMsg}</p>
                </div>
              )}

              {/* SEPA-Lastschrift */}
              <label className="flex items-center gap-2 cursor-pointer select-none pt-1">
                <input
                  type="checkbox"
                  checked={sepaLastschrift}
                  onChange={e => { setSepaLastschrift(e.target.checked); mutSepa.mutate(e.target.checked) }}
                  disabled={mutSepa.isPending}
                  className="w-4 h-4 accent-blue-600"
                />
                <span className="text-sm text-gray-700">SEPA-Lastschrift</span>
                {mutSepa.isPending && <span className="text-xs text-gray-400">…</span>}
              </label>

              {/* Freigabe-Aktionen */}
              <div className="flex gap-3 pt-2">
                <Button
                  onClick={() => mutFreigabeGenehmigen.mutate()}
                  disabled={!kannFreigeben || mutFreigabeGenehmigen.isPending}
                  variant="primary"
                >
                  {mutFreigabeGenehmigen.isPending ? 'Wird freigegeben…' : 'Freigeben'}
                </Button>
              </div>
              {!kannFreigeben && (
                <p className="text-xs text-gray-400">
                  {effektivesAufwandskontoId ? '' : 'Bitte zuerst ein Aufwandskonto wählen.'}
                </p>
              )}
            </>
          ) : (
            /* ── IDENTIFIKATIONS-MODUS (pruefung_match / nicht_erkannt) ── */
            <>
              {/* Karte 1: Kreditor */}
              <DimensionCard
                titel="Kreditor"
                erkannt={rechnung.erkennungs_stufe === '3'
                  ? !!kreditorId
                  : !!(rechnung.kreditor && (!konfidenz || konfidenz.kreditor >= 0.9))}
                erkannterWert={rechnung.erkennungs_stufe === '3'
                  ? kreditoren?.find(k => k.id === kreditorId)?.name
                  : rechnung.kreditor_name}
              >
                {rechnung.erkennungs_stufe === '3' && duplikatKandidaten.length > 0 && !kreditorId && (
                  <div className="mb-2 space-y-1">
                    <p className="text-xs font-medium text-gray-500">Mögliche Übereinstimmungen:</p>
                    {duplikatKandidaten.slice(0, 5).map(k => (
                      <div key={k.id} className="flex items-center justify-between bg-white border rounded px-2 py-1 text-xs">
                        <div className="min-w-0 mr-2">
                          <span className="font-medium text-gray-800 truncate block">{k.name}</span>
                          <span className="text-gray-400 font-mono">{k.kreditorennummer}{k.iban ? ` · ${k.iban}` : ''}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className={`font-mono ${k.score >= 0.9 ? 'text-green-600' : k.score >= 0.7 ? 'text-yellow-600' : 'text-gray-400'}`}>
                            {(k.score * 100).toFixed(0)}%
                          </span>
                          <button onClick={() => setKreditorId(k.id)} className="text-blue-600 hover:underline font-medium">
                            Verwenden
                          </button>
                        </div>
                      </div>
                    ))}
                    <div className="text-center text-xs text-gray-400">— oder manuell wählen —</div>
                  </div>
                )}

                <select
                  value={kreditorId}
                  onChange={e => setKreditorId(e.target.value)}
                  className="border rounded px-2 py-1.5 text-sm w-full"
                >
                  <option value="">— Kreditor wählen —</option>
                  {(kreditoren ?? []).map(k => (
                    <option key={k.id} value={k.id}>
                      {k.kreditorennummer ? `[${k.kreditorennummer}] ` : ''}{k.name}
                    </option>
                  ))}
                </select>

                {rechnung.erkennungs_stufe === '3' && (
                  <div className="mt-2">
                    {!zeigeNeuForm ? (
                      <button type="button" onClick={() => setZeigeNeuForm(true)} className="text-xs text-blue-600 hover:underline">
                        + Neuen Kreditor anlegen
                      </button>
                    ) : (
                      <div className="border rounded p-2 space-y-2 bg-white text-xs">
                        <p className="font-semibold text-gray-600">Neuer Kreditor</p>
                        <input type="text" value={neuName} onChange={e => { setNeuName(e.target.value); setDubWarn([]) }} placeholder="Name *" className="border rounded px-2 py-1 text-sm w-full" />
                        <input type="text" value={neuIban} onChange={e => { setNeuIban(e.target.value); setDubWarn([]) }} placeholder="IBAN (optional)" className="border rounded px-2 py-1 text-sm w-full font-mono" />
                        {dubWarn.length > 0 && (
                          <div className="rounded bg-orange-50 border border-orange-200 p-2 space-y-1 text-orange-800">
                            <p className="font-semibold">Mögliche Duplikate!</p>
                            {dubWarn.map(k => (
                              <div key={k.id} className="flex justify-between items-center">
                                <span>{k.name} — {(k.score * 100).toFixed(0)}%</span>
                                <button onClick={() => { setKreditorId(k.id); setZeigeNeuForm(false); setDubWarn([]) }} className="text-blue-600 hover:underline ml-2 font-medium">Verwenden</button>
                              </div>
                            ))}
                            <button type="button" onClick={() => mutNeuerKreditor.mutate({ name: neuName.trim(), iban: neuIban.replace(/\s/g,'').toUpperCase() || undefined })} className="text-red-600 hover:underline text-xs">Trotzdem neu anlegen</button>
                          </div>
                        )}
                        <div className="flex gap-2 pt-1">
                          <Button onClick={handleNeuKreditorAnlegen} disabled={!neuName.trim() || mutNeuerKreditor.isPending}>Anlegen</Button>
                          <Button variant="secondary" onClick={() => { setZeigeNeuForm(false); setDubWarn([]) }}>Abbrechen</Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </DimensionCard>

              {/* Karte 2: Objekt */}
              <DimensionCard
                titel="Objekt"
                erkannt={!!(rechnung.objekt && (!konfidenz || konfidenz.objekt >= 0.85))}
                erkannterWert={rechnung.objekt_bezeichnung}
              >
                <select
                  value={objektId}
                  onChange={e => { setObjektId(e.target.value); setWirtschaftsjahrId(''); setAufwandskontoId(''); setAufwandskontoAendern(false) }}
                  className="border rounded px-2 py-1.5 text-sm w-full"
                >
                  <option value="">— Objekt wählen —</option>
                  {(objekte ?? []).map(o => (
                    <option key={o.id} value={o.id}>{o.bezeichnung}</option>
                  ))}
                </select>
              </DimensionCard>

              {/* Karte 3: Aufwandskonto mit "Sachkonto ändern"-Toggle */}
              <DimensionCard
                titel="Aufwandskonto"
                erkannt={aufwandskontoErkannt}
                erkannterWert={rechnung.aufwandskonto_label}
              >
                {aufwandskontoErkannt && !aufwandskontoAendern ? (
                  <button
                    type="button"
                    onClick={() => setAufwandskontoAendern(true)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Sachkonto ändern
                  </button>
                ) : (
                  <>
                    {(objektId || rechnung.objekt) && (
                      <WjSelektor
                        wirtschaftsjahre={wirtschaftsjahre}
                        wirtschaftsjahrId={wirtschaftsjahrId}
                        onChange={id => { setWirtschaftsjahrId(id); setAufwandskontoId('') }}
                      />
                    )}
                    <select
                      value={aufwandskontoId}
                      onChange={e => setAufwandskontoId(e.target.value)}
                      className="border rounded px-2 py-1.5 text-sm w-full"
                      disabled={!(objektId || rechnung.objekt)}
                    >
                      <option value="">— Aufwandskonto wählen (50xxx–55xxx) —</option>
                      {aufwandskonten.map(k => (
                        <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>
                      ))}
                    </select>
                    {aufwandskontoAendern && (
                      <button
                        type="button"
                        onClick={() => { setAufwandskontoAendern(false); setAufwandskontoId('') }}
                        className="text-xs text-gray-400 hover:underline mt-1"
                      >
                        Abbrechen
                      </button>
                    )}
                    {!(objektId || rechnung.objekt) && (
                      <p className="text-xs text-gray-400 mt-1">Erst Objekt wählen</p>
                    )}
                  </>
                )}
              </DimensionCard>

              {/* Lernhinweis */}
              <div className="bg-amber-50 border border-amber-200 rounded px-3 py-2 text-xs text-amber-800">
                Diese Zuordnung wird für zukünftige Rechnungen dieses Kreditors mit gleichem Leistungstext angewendet.
              </div>
              <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                <input type="checkbox" checked={!lernen} onChange={e => setLernen(!e.target.checked)} className="rounded" />
                Einzelfall — keine Regel speichern
              </label>

              {/* SEPA-Lastschrift */}
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={sepaLastschrift}
                  onChange={e => { setSepaLastschrift(e.target.checked); mutSepa.mutate(e.target.checked) }}
                  disabled={mutSepa.isPending}
                  className="w-4 h-4 accent-blue-600"
                />
                <span className="text-sm text-gray-700">SEPA-Lastschrift</span>
                {mutSepa.isPending && <span className="text-xs text-gray-400">…</span>}
              </label>

              {/* Fehleranzeige */}
              {mutErrorMsg && (
                <div className="rounded bg-red-50 border border-red-200 p-3">
                  <p className="text-sm text-red-700">{mutErrorMsg}</p>
                </div>
              )}

              {/* Identifikations-Aktionen */}
              <div className="flex gap-3 pt-2">
                <Button onClick={() => mutSpeichern.mutate()} disabled={!kannSpeichern || mutSpeichern.isPending}>
                  Identifizieren + Speichern
                </Button>
                <Button
                  onClick={() => mutDirektfreigeben.mutate()}
                  disabled={!kannDirektfreigeben || mutDirektfreigeben.isPending}
                  title={!kannDirektfreigeben ? 'Betrag über Ihrem Freigabelimit — wird nach Identifikation eskaliert' : undefined}
                  variant={kannDirektfreigeben ? 'primary' : 'secondary'}
                >
                  Identifizieren + Freigeben
                </Button>
              </div>
            </>
          )}

          {/* Ablehnen — in beiden Modi */}
          <div className="border-t pt-4 space-y-2">
            <div className="text-xs font-semibold text-gray-500 uppercase">Ablehnen</div>
            <textarea
              value={begruendung}
              onChange={e => setBegruendung(e.target.value)}
              placeholder="Begründung (Pflicht)"
              rows={2}
              className="border rounded px-2 py-1.5 text-sm w-full resize-none"
            />
            <Button
              variant="danger"
              onClick={() => mutAblehnen.mutate()}
              disabled={!begruendung.trim() || mutAblehnen.isPending}
            >
              Ablehnen
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex gap-2">
      <span className="text-gray-500 w-36 shrink-0">{label}</span>
      <span className="text-gray-800 break-all">{value || '—'}</span>
    </div>
  )
}

function WjSelektor({
  wirtschaftsjahre,
  wirtschaftsjahrId,
  onChange,
}: {
  wirtschaftsjahre: Wirtschaftsjahr[] | undefined
  wirtschaftsjahrId: string
  onChange: (id: string) => void
}) {
  if (!wirtschaftsjahre?.length) return null
  const sorted = [...wirtschaftsjahre].sort((a, b) => b.jahr - a.jahr)
  return (
    <div className="mb-2">
      <label className="text-xs text-gray-500 mb-0.5 block">Wirtschaftsjahr</label>
      <select
        value={wirtschaftsjahrId}
        onChange={e => onChange(e.target.value)}
        className="border rounded px-2 py-1 text-sm w-full bg-white"
      >
        {sorted.map(wj => (
          <option key={wj.id} value={wj.id}>
            {wj.jahr}{wj.status === 'abgeschlossen' ? ' (abgeschlossen)' : ' (offen)'}
          </option>
        ))}
      </select>
    </div>
  )
}

function DimensionCard({
  titel, erkannt, erkannterWert, children,
}: {
  titel: string; erkannt: boolean; erkannterWert: string | null | undefined; children: React.ReactNode
}) {
  return (
    <div className={`border rounded-lg p-3 ${erkannt ? 'border-green-300 bg-green-50' : 'border-orange-300 bg-orange-50'}`}>
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{titel}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${erkannt ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>
          {erkannt ? '✓ erkannt' : '— offen'}
        </span>
      </div>
      {erkannt && erkannterWert ? (
        <p className="text-sm text-gray-700 mb-1">{erkannterWert}</p>
      ) : null}
      {children}
    </div>
  )
}
