import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { wkzApi, type WKZVorlageCreate } from '../../../api/wkz'
import { Button } from '../../../components/ui/Button'
import { useObjektStore } from '../../../stores/objekt'

interface SplitRow {
  kontonummer: string
  bezeichnung: string
  betrag: string
}

const RHYTHMUS_OPTIONEN = [
  { value: 'monatlich', label: 'Monatlich' },
  { value: 'zweimonatlich', label: 'Zweimonatlich' },
  { value: 'quartalsweise', label: 'Quartalsweise' },
  { value: 'halbjaehrlich', label: 'Halbjährlich' },
  { value: 'jaehrlich', label: 'Jährlich' },
  { value: 'frei', label: 'Frei (manuell)' },
]

const WOCHENENDE_OPTIONEN = [
  { value: 'zurueck', label: 'Montag danach' },
  { value: 'vor', label: 'Freitag davor' },
  { value: 'unveraendert', label: 'Unverändert' },
]

function summe(splits: SplitRow[]): number {
  return splits.reduce((s, r) => s + (parseFloat(r.betrag) || 0), 0)
}

export default function VorlageWizard() {
  const { selectedId: objektId } = useObjektStore()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // URL-Parameter (vorausgefüllt aus Rechnung)
  const paramRechnungId   = searchParams.get('rechnung_id') ?? ''
  const paramKreditorId   = searchParams.get('kreditor_id') ?? ''
  const paramBezeichnung  = searchParams.get('bezeichnung') ?? ''
  const paramBetrag       = searchParams.get('betrag') ?? ''

  // Schritt 1–4
  const [schritt, setSchritt] = useState(1)

  // Stammdaten
  const [kreditorId, setKreditorId] = useState(paramKreditorId)
  const [bezeichnung, setBezeichnung] = useState(paramBezeichnung)
  const [typ, setTyp] = useState<'bescheid' | 'vertrag'>('bescheid')
  const [bescheidPflicht, setBescheidPflicht] = useState(true)

  // Rhythmus & Zeitraum
  const [rhythmus, setRhythmus] = useState('quartalsweise')
  const [ersteFaelligkeit, setErsteFaelligkeit] = useState('')
  const [gueltigAb, setGueltigAb] = useState('')
  const [gueltigBis, setGueltigBis] = useState('')
  const [beiWochenende, setBeiWochenende] = useState('zurueck')

  // Splits (Betrag aus Rechnung vorausfüllen wenn vorhanden)
  const [splits, setSplits] = useState<SplitRow[]>([
    { kontonummer: '', bezeichnung: paramBezeichnung, betrag: paramBetrag },
  ])

  // Bank-Match
  const [toleranzBetrag, setToleranzBetrag] = useState('5.00')
  const [toleranzTage, setToleranzTage] = useState('14')
  const [sepaMandatId, setSepaMandatId] = useState('')

  const [fehler, setFehler] = useState('')

  // Kreditoren laden (für Dropdown)
  const { data: kreditoren = [] } = useQuery({
    queryKey: ['kreditoren-liste'],
    queryFn: () =>
      import('../../../api/rechnungen').then(m =>
        m.rechnungenApi.kreditoren().catch(() => [])
      ),
  })

  const mutation = useMutation({
    mutationFn: (data: WKZVorlageCreate) =>
      wkzApi.vorlageAnlegen(objektId!, data),
    onSuccess: v => navigate(`../${v.id}`),
    onError: (e: unknown) =>
      setFehler((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Fehler'),
  })

  function handleSplitChange(i: number, field: keyof SplitRow, val: string) {
    setSplits(prev => prev.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)))
  }

  function addSplit() {
    setSplits(prev => [...prev, { kontonummer: '', bezeichnung: '', betrag: '' }])
  }

  function removeSplit(i: number) {
    setSplits(prev => prev.filter((_, idx) => idx !== i))
  }

  const gesamtbetrag = summe(splits).toFixed(2)

  function handleSubmit() {
    setFehler('')
    if (!kreditorId || !bezeichnung || !ersteFaelligkeit || !gueltigAb) {
      setFehler('Bitte alle Pflichtfelder ausfüllen.')
      return
    }
    if (splits.some(s => !s.kontonummer || !s.betrag)) {
      setFehler('Bitte alle Splits vollständig ausfüllen.')
      return
    }

    mutation.mutate({
      objekt: objektId!,
      kreditor: kreditorId,
      bezeichnung,
      typ,
      betrag_gesamt: gesamtbetrag,
      rhythmus,
      erste_faelligkeit: ersteFaelligkeit,
      bei_wochenende: beiWochenende,
      toleranz_betrag: toleranzBetrag,
      toleranz_tage: parseInt(toleranzTage),
      sepa_mandat_id: sepaMandatId,
      bescheid_pflicht: bescheidPflicht,
      gueltig_ab: gueltigAb,
      gueltig_bis: gueltigBis || null,
      rechnung_id: paramRechnungId || null,
      splits: splits.map((s, i) => ({
        kontonummer: s.kontonummer,
        bezeichnung: s.bezeichnung,
        betrag: s.betrag,
        reihenfolge: i,
      })),
    })
  }

  if (!objektId) {
    return <p className="text-gray-500 p-4">Bitte ein Objekt auswählen.</p>
  }

  return (
    <div className="p-4 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate(-1)}
          className="text-gray-500 hover:text-gray-800 text-sm"
        >
          ← Zurück
        </button>
        <h1 className="text-xl font-semibold">Neue Vorlage anlegen</h1>
      </div>

      {paramRechnungId && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2.5 text-sm text-blue-800">
          <span className="font-medium">Aus Rechnung übernommen</span> — Kreditor, Bezeichnung und Betrag sind vorausgefüllt.
          Der DMS-Bezug zur Originalrechnung wird automatisch gespeichert.
        </div>
      )}

      {/* Schrittanzeige */}
      <div className="flex gap-2 text-sm">
        {[1, 2, 3, 4].map(s => (
          <button
            key={s}
            onClick={() => setSchritt(s)}
            className={`px-3 py-1 rounded ${
              schritt === s
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            Schritt {s}
          </button>
        ))}
      </div>

      {/* Schritt 1: Stammdaten */}
      {schritt === 1 && (
        <div className="space-y-4">
          <h2 className="font-medium">Kreditor & Stammdaten</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Kreditor *
            </label>
            <select
              value={kreditorId}
              onChange={e => setKreditorId(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            >
              <option value="">— Bitte wählen —</option>
              {kreditoren.map((k: { id: string; name: string }) => (
                <option key={k.id} value={k.id}>{k.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Bezeichnung *
            </label>
            <input
              type="text"
              value={bezeichnung}
              onChange={e => setBezeichnung(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              placeholder="z.B. Stadt Frankfurt — Versorgungsgebühren"
            />
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Typ *</label>
              <select
                value={typ}
                onChange={e => {
                  const t = e.target.value as 'bescheid' | 'vertrag'
                  setTyp(t)
                  setBescheidPflicht(t === 'bescheid')
                }}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              >
                <option value="bescheid">Bescheid</option>
                <option value="vertrag">Vertrag</option>
              </select>
            </div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={bescheidPflicht}
                  onChange={e => setBescheidPflicht(e.target.checked)}
                />
                Bescheid-PDF erforderlich
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Schritt 2: Rhythmus & Zeitraum */}
      {schritt === 2 && (
        <div className="space-y-4">
          <h2 className="font-medium">Rhythmus & Zeitraum</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Rhythmus *</label>
            <select
              value={rhythmus}
              onChange={e => setRhythmus(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            >
              {RHYTHMUS_OPTIONEN.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Erste Fälligkeit *
              </label>
              <input
                type="date"
                value={ersteFaelligkeit}
                onChange={e => setErsteFaelligkeit(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Bei Wochenende
              </label>
              <select
                value={beiWochenende}
                onChange={e => setBeiWochenende(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              >
                {WOCHENENDE_OPTIONEN.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Gültig ab *
              </label>
              <input
                type="date"
                value={gueltigAb}
                onChange={e => setGueltigAb(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Gültig bis (leer = unbefristet)
              </label>
              <input
                type="date"
                value={gueltigBis}
                onChange={e => setGueltigBis(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              />
            </div>
          </div>
        </div>
      )}

      {/* Schritt 3: Splits */}
      {schritt === 3 && (
        <div className="space-y-4">
          <h2 className="font-medium">Splits (Aufwandskonten)</h2>
          <div className="space-y-2">
            {splits.map((split, i) => (
              <div key={i} className="flex gap-2 items-start">
                <input
                  type="text"
                  value={split.kontonummer}
                  onChange={e => handleSplitChange(i, 'kontonummer', e.target.value)}
                  placeholder="50100"
                  maxLength={8}
                  className="w-24 border border-gray-300 rounded px-2 py-1.5 text-sm"
                />
                <input
                  type="text"
                  value={split.bezeichnung}
                  onChange={e => handleSplitChange(i, 'bezeichnung', e.target.value)}
                  placeholder="Bezeichnung"
                  className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm"
                />
                <input
                  type="number"
                  value={split.betrag}
                  onChange={e => handleSplitChange(i, 'betrag', e.target.value)}
                  placeholder="0.00"
                  step="0.01"
                  min="0"
                  className="w-28 border border-gray-300 rounded px-2 py-1.5 text-sm text-right"
                />
                {splits.length > 1 && (
                  <button
                    onClick={() => removeSplit(i)}
                    className="text-red-500 hover:text-red-700 text-sm px-1"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
          <button
            onClick={addSplit}
            className="text-sm text-blue-600 hover:underline"
          >
            + Split hinzufügen
          </button>
          <div className="flex justify-between items-center text-sm font-medium border-t pt-2">
            <span>Gesamtbetrag</span>
            <span className={summe(splits) <= 0 ? 'text-red-600' : 'text-gray-900'}>
              {Number(gesamtbetrag).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
            </span>
          </div>
        </div>
      )}

      {/* Schritt 4: Bank-Match */}
      {schritt === 4 && (
        <div className="space-y-4">
          <h2 className="font-medium">Bank-Match Konfiguration</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Toleranz Betrag (€)
              </label>
              <input
                type="number"
                value={toleranzBetrag}
                onChange={e => setToleranzBetrag(e.target.value)}
                step="0.01"
                min="0"
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Toleranz Tage
              </label>
              <input
                type="number"
                value={toleranzTage}
                onChange={e => setToleranzTage(e.target.value)}
                min="0"
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              SEPA-Mandats-ID (optional)
            </label>
            <input
              type="text"
              value={sepaMandatId}
              onChange={e => setSepaMandatId(e.target.value)}
              maxLength={35}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              placeholder="DE98ZZZ09999999999"
            />
            <p className="text-xs text-gray-500 mt-1">
              Ohne Mandats-ID erfolgt der Bank-Match nur über IBAN+Betrag+Periode.
            </p>
          </div>

          {/* Vorschau */}
          <div className="bg-gray-50 rounded p-4 text-sm space-y-2">
            <p className="font-medium">Zusammenfassung</p>
            <p><span className="text-gray-500">Bezeichnung:</span> {bezeichnung || '–'}</p>
            <p><span className="text-gray-500">Rhythmus:</span> {rhythmus}</p>
            <p><span className="text-gray-500">Gesamtbetrag:</span>{' '}
              {Number(gesamtbetrag).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
            </p>
            <p><span className="text-gray-500">Splits:</span> {splits.length} Position(en)</p>
          </div>
        </div>
      )}

      {/* Fehlermeldung */}
      {fehler && <p className="text-red-600 text-sm">{fehler}</p>}

      {/* Navigation */}
      <div className="flex justify-between pt-2">
        <Button
          variant="secondary"
          onClick={() => setSchritt(s => Math.max(1, s - 1))}
          disabled={schritt === 1}
        >
          Zurück
        </Button>
        {schritt < 4 ? (
          <Button variant="primary" onClick={() => setSchritt(s => Math.min(4, s + 1))}>
            Weiter
          </Button>
        ) : (
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Wird gespeichert…' : 'Vorlage anlegen'}
          </Button>
        )}
      </div>
    </div>
  )
}
