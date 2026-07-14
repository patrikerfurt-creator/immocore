import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { rechnungenApi } from '../../api/rechnungen'
import { objekteApi } from '../../api/objekte'
import { buchhaltungApi } from '../../api/buchhaltung'
import type { AmpelErgebnis, Einheit, Kreditor, Konto, ObjektList, Rechnung } from '../../types'
import { Ampelpunkt } from './Ampel'

interface FormState {
  kreditor_id: string
  objekt_id: string
  aufwandskonto_id: string
  rechnungsnummer: string
  rechnungsdatum: string
  faelligkeitsdatum: string
  betrag_netto: string
  betrag_brutto: string
  mwst_satz: string
  betrag_haushaltsnah: string
  ist_schlussrechnung: boolean
  ist_gutschrift: boolean
  sepa_lastschrift: boolean
  skonto_prozent: string
  skonto_betrag: string
  skonto_faellig_bis: string
  kostenverursacher_id: string
  leistungsbeschreibung: string
}

const LEER: FormState = {
  kreditor_id: '', objekt_id: '', aufwandskonto_id: '', rechnungsnummer: '',
  rechnungsdatum: '', faelligkeitsdatum: '', betrag_netto: '', betrag_brutto: '',
  mwst_satz: '', betrag_haushaltsnah: '', ist_schlussrechnung: false,
  ist_gutschrift: false, sepa_lastschrift: false,
  skonto_prozent: '', skonto_betrag: '', skonto_faellig_bis: '',
  kostenverursacher_id: '', leistungsbeschreibung: '',
}

interface SplitRow { aufwandskonto: string; betrag: string }

// Formularfeld → Schlüssel im Ampel-Detail (erkennung_details)
const FELD_AMPEL: Record<string, string> = {
  kreditor_id: 'kreditor',
  betrag_brutto: 'betrag_brutto',
  rechnungsnummer: 'rechnungsnummer',
  rechnungsdatum: 'rechnungsdatum',
  betrag_haushaltsnah: 'betrag_haushaltsnah',
  skonto_prozent: 'skonto',
  kostenverursacher_id: 'kostenverursacher',
}

function istAufwandskonto(k: Konto): boolean {
  const nr = Number(k.kontonummer)
  return k.direktes_buchen || (nr >= 50000 && nr <= 55999)
}

export default function RechnungErfassen() {
  const { id } = useParams<{ id?: string }>()
  const navigate = useNavigate()

  const [form, setForm] = useState<FormState>(LEER)
  const [rechnung, setRechnung] = useState<Rechnung | null>(null)
  const [ampel, setAmpel] = useState<AmpelErgebnis | null>(null)
  const [kreditoren, setKreditoren] = useState<Kreditor[]>([])
  const [objekte, setObjekte] = useState<ObjektList[]>([])
  const [einheiten, setEinheiten] = useState<Einheit[]>([])
  const [konten, setKonten] = useState<Konto[]>([])
  const [einheitSuche, setEinheitSuche] = useState('')
  const [gelbGeprueft, setGelbGeprueft] = useState(false)
  const [busy, setBusy] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const pdfUrlRef = useRef<string | null>(null)
  const [aufteilen, setAufteilen] = useState(false)
  const [splits, setSplits] = useState<SplitRow[]>([
    { aufwandskonto: '', betrag: '' }, { aufwandskonto: '', betrag: '' },
  ])

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm(f => ({ ...f, [k]: v }))

  // Stammdaten laden
  useEffect(() => {
    rechnungenApi.kreditoren().then(setKreditoren).catch(() => {})
    objekteApi.list().then(setObjekte).catch(() => {})
  }, [])

  // Bestehende Rechnung laden
  useEffect(() => {
    if (!id) return
    rechnungenApi.get(id).then(r => {
      setRechnung(r)
      setForm({
        kreditor_id: r.kreditor ?? '', objekt_id: r.objekt ?? '',
        aufwandskonto_id: r.aufwandskonto ?? '', rechnungsnummer: r.rechnungsnummer ?? '',
        rechnungsdatum: r.rechnungsdatum ?? '', faelligkeitsdatum: r.faelligkeitsdatum ?? '',
        betrag_netto: r.betrag_netto ?? '', betrag_brutto: r.betrag_brutto ?? '',
        mwst_satz: r.mwst_satz ?? '', betrag_haushaltsnah: r.betrag_haushaltsnah ?? '',
        ist_schlussrechnung: r.ist_schlussrechnung, ist_gutschrift: r.ist_gutschrift,
        sepa_lastschrift: r.sepa_lastschrift, skonto_prozent: r.skonto_prozent ?? '',
        skonto_betrag: r.skonto_betrag ?? '', skonto_faellig_bis: r.skonto_faellig_bis ?? '',
        kostenverursacher_id: r.kostenverursacher ?? '', leistungsbeschreibung: r.leistungsbeschreibung ?? '',
      })
      if (r.splits && r.splits.length >= 2) {
        setAufteilen(true)
        setSplits(r.splits.map(s => ({ aufwandskonto: s.aufwandskonto, betrag: s.betrag })))
      }
      if (r.erkennung_ampel) {
        setAmpel({
          ampel: r.erkennung_ampel,
          gesamt_konfidenz: Number(r.erkennung_gesamt_konfidenz ?? 0),
          felder: r.erkennung_details ?? {},
        })
      }
    }).catch(() => setFehler('Rechnung konnte nicht geladen werden.'))
  }, [id])

  // PDF-Vorschau laden (parallel neben dem Formular)
  useEffect(() => {
    if (!id || !(rechnung?.pdf_upload || rechnung?.pfad)) return
    let cancelled = false
    rechnungenApi.getPdfBlobUrl(id).then(url => {
      if (cancelled) { URL.revokeObjectURL(url); return }
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current)
      pdfUrlRef.current = url
      setPdfUrl(url)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [id, rechnung?.pdf_upload])

  // Blob-URL beim Verlassen freigeben
  useEffect(() => () => { if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current) }, [])

  // Objektabhängige Listen (Einheiten für Kostenverursacher, Aufwandskonten)
  useEffect(() => {
    if (!form.objekt_id) { setEinheiten([]); setKonten([]); return }
    objekteApi.listEinheiten({ objekt: form.objekt_id }).then(setEinheiten).catch(() => setEinheiten([]))
    buchhaltungApi.konten(form.objekt_id).then(ks => setKonten(ks.filter(istAufwandskonto))).catch(() => setKonten([]))
  }, [form.objekt_id])

  const einheitenGefiltert = useMemo(() => {
    const q = einheitSuche.trim().toLowerCase()
    if (!q) return einheiten
    return einheiten.filter(e =>
      e.einheit_nr.toLowerCase().includes(q) || (e.lage ?? '').toLowerCase().includes(q))
  }, [einheiten, einheitSuche])

  const feldAmpel = (feld: keyof FormState) => {
    const key = FELD_AMPEL[feld]
    return key && ampel?.felder?.[key] ? ampel.felder[key] : null
  }

  const kritischRot = useMemo(
    () => !!ampel && Object.entries(ampel.felder).some(
      ([n, f]) => f.ampel === 'rot' && ['kreditor', 'betrag_brutto', 'rechnungsnummer'].includes(n)),
    [ampel])
  const hatGelb = useMemo(
    () => !!ampel && Object.values(ampel.felder).some(f => f.ampel === 'gelb'), [ampel])

  const ocrAusfuehren = async () => {
    if (!id) return
    setBusy(true); setFehler(null)
    try {
      const res = await rechnungenApi.ocr(id)
      const e = res.extraktion as Record<string, string | boolean | null>
      setForm(f => ({
        ...f,
        rechnungsnummer: (e.rechnungsnummer as string) ?? f.rechnungsnummer,
        rechnungsdatum: (e.rechnungsdatum as string) ?? f.rechnungsdatum,
        faelligkeitsdatum: (e.faelligkeitsdatum as string) ?? f.faelligkeitsdatum,
        betrag_netto: e.betrag_netto != null ? String(e.betrag_netto) : f.betrag_netto,
        betrag_brutto: e.betrag_brutto != null ? String(e.betrag_brutto) : f.betrag_brutto,
        mwst_satz: e.mwst_satz != null ? String(e.mwst_satz) : f.mwst_satz,
        betrag_haushaltsnah: e.betrag_haushaltsnah != null ? String(e.betrag_haushaltsnah) : f.betrag_haushaltsnah,
        skonto_prozent: e.skonto_prozent != null ? String(e.skonto_prozent) : f.skonto_prozent,
        skonto_betrag: e.skonto_betrag != null ? String(e.skonto_betrag) : f.skonto_betrag,
        skonto_faellig_bis: (e.skonto_faellig_bis as string) ?? f.skonto_faellig_bis,
        ist_schlussrechnung: Boolean(e.ist_schlussrechnung) || f.ist_schlussrechnung,
        ist_gutschrift: Boolean(e.ist_gutschrift) || f.ist_gutschrift,
        leistungsbeschreibung: (e.leistungsbeschreibung as string) ?? f.leistungsbeschreibung,
      }))
      setAmpel(res.ampel)
    } catch {
      setFehler('OCR fehlgeschlagen.')
    } finally { setBusy(false) }
  }

  const speichern = async (modus: 'entwurf' | 'zur_freigabe' | 'freigeben') => {
    setBusy(true); setFehler(null)
    try {
      const payload: Record<string, unknown> = { ...form, modus }
      if (id) payload.id = id
      if (aufteilen) {
        payload.splits = splits
          .filter(s => s.aufwandskonto && s.betrag)
          .map(s => ({ aufwandskonto: s.aufwandskonto, betrag: s.betrag.replace(',', '.') }))
      } else {
        payload.splits = []   // ohne Aufteilung: evtl. vorhandene Splits entfernen
      }
      const r = await rechnungenApi.erfassen(payload as Record<string, unknown> & { modus: typeof modus })
      setRechnung(r)
      if (r.erkennung_ampel) {
        setAmpel({
          ampel: r.erkennung_ampel,
          gesamt_konfidenz: Number(r.erkennung_gesamt_konfidenz ?? 0),
          felder: r.erkennung_details ?? {},
        })
      }
      navigate('/rechnungen/inbox')
    } catch (e) {
      const data = (e as { response?: { data?: { error?: unknown } } }).response?.data?.error
      setFehler(typeof data === 'string' ? data : 'Speichern fehlgeschlagen — bitte Pflichtfelder prüfen.')
    } finally { setBusy(false) }
  }

  const splitSumme = splits.reduce((a, r) => a + (parseFloat(r.betrag.replace(',', '.')) || 0), 0)
  const brutto = parseFloat((form.betrag_brutto || '').replace(',', '.')) || 0
  const splitPasst = Math.abs(splitSumme - brutto) < 0.005
  const freigebenGesperrt = kritischRot || (hatGelb && !gelbGeprueft) || (aufteilen && !splitPasst)

  const feldWrap = (feld: keyof FormState, label: string, node: ReactNode) => {
    const fa = feldAmpel(feld)
    return (
      <label className="block">
        <span className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
          {label}
          {fa && <Ampelpunkt ampel={fa.ampel} title={fa.hinweis} />}
        </span>
        {node}
        {fa && fa.ampel !== 'gruen' && fa.hinweis && (
          <span className="block text-xs text-amber-700 mt-0.5">{fa.hinweis}</span>
        )}
      </label>
    )
  }

  const inp = 'w-full border rounded px-2 py-1.5 text-sm'

  // Split-Helfer
  const setSplitRow = (i: number, feld: keyof SplitRow, v: string) =>
    setSplits(prev => prev.map((r, idx) => idx === i ? { ...r, [feld]: v } : r))
  const addSplit = () => setSplits(prev => [...prev, { aufwandskonto: '', betrag: '' }])
  const removeSplit = (i: number) => setSplits(prev => prev.length <= 2 ? prev : prev.filter((_, idx) => idx !== i))

  return (
    <div className={pdfUrl ? 'flex items-start min-h-screen' : ''}>
    <div className={pdfUrl ? 'flex-1 min-w-0 p-6 overflow-y-auto' : 'p-6 max-w-3xl'}>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-800">
          {id ? 'Rechnung bearbeiten' : 'Rechnung erfassen'}
        </h1>
        {id && (rechnung?.pdf_upload || rechnung?.pfad) && (
          <div className="flex gap-2">
            <button onClick={ocrAusfuehren} disabled={busy}
                    className="px-3 py-1.5 text-sm rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-50">
              OCR-Vorbefüllung
            </button>
          </div>
        )}
      </div>

      {/* Verifikations-Ampel gesamt */}
      <div className="mb-5 p-3 border rounded bg-gray-50 flex items-center justify-between">
        <Ampelpunkt ampel={ampel?.ampel ?? null} gross konfidenz={ampel?.gesamt_konfidenz} />
        {hatGelb && (
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={gelbGeprueft} onChange={e => setGelbGeprueft(e.target.checked)} />
            Gelbe Felder geprüft
          </label>
        )}
      </div>

      {fehler && <div className="mb-3 text-sm text-red-600">{fehler}</div>}

      <div className="grid grid-cols-2 gap-4">
        {feldWrap('kreditor_id', 'Kreditor', (
          <select className={inp} value={form.kreditor_id} onChange={e => set('kreditor_id', e.target.value)}>
            <option value="">— wählen —</option>
            {kreditoren.map(k => <option key={k.id} value={k.id}>{k.name}{k.kreditorennummer ? ` [${k.kreditorennummer}]` : ''}</option>)}
          </select>
        ))}
        {feldWrap('objekt_id', 'Objekt', (
          <select className={inp} value={form.objekt_id} onChange={e => { set('objekt_id', e.target.value); set('aufwandskonto_id', ''); set('kostenverursacher_id', '') }}>
            <option value="">— wählen —</option>
            {objekte.map(o => <option key={o.id} value={o.id}>{o.bezeichnung}</option>)}
          </select>
        ))}

        {feldWrap('rechnungsnummer', 'Rechnungsnummer', (
          <input className={inp} value={form.rechnungsnummer} onChange={e => set('rechnungsnummer', e.target.value)} />
        ))}
        {feldWrap('rechnungsdatum', 'Rechnungsdatum', (
          <input type="date" className={inp} value={form.rechnungsdatum} onChange={e => set('rechnungsdatum', e.target.value)} />
        ))}

        {feldWrap('betrag_netto', 'Betrag netto', (
          <input className={inp} value={form.betrag_netto} onChange={e => set('betrag_netto', e.target.value)} inputMode="decimal" />
        ))}
        {feldWrap('betrag_brutto', 'Betrag brutto', (
          <input className={inp} value={form.betrag_brutto} onChange={e => set('betrag_brutto', e.target.value)} inputMode="decimal" />
        ))}

        {feldWrap('mwst_satz', 'MwSt-Satz (%)', (
          <input className={inp} value={form.mwst_satz} onChange={e => set('mwst_satz', e.target.value)} inputMode="decimal" />
        ))}
        {feldWrap('faelligkeitsdatum', 'Fälligkeit', (
          <input type="date" className={inp} value={form.faelligkeitsdatum} onChange={e => set('faelligkeitsdatum', e.target.value)} />
        ))}

        {feldWrap('aufwandskonto_id', 'Aufwandskonto (50000–55999)', (
          <select className={inp} value={form.aufwandskonto_id} onChange={e => set('aufwandskonto_id', e.target.value)}>
            <option value="">— wählen —</option>
            {konten.map(k => <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>)}
          </select>
        ))}
        {feldWrap('betrag_haushaltsnah', '§35a Lohnkostenanteil', (
          <input className={inp} value={form.betrag_haushaltsnah} onChange={e => set('betrag_haushaltsnah', e.target.value)} inputMode="decimal" />
        ))}
      </div>

      {/* Kostenverursacher-Dropdown mit Suche */}
      <div className="mt-4">
        <span className="text-xs text-gray-500 mb-1 block">Kostenverursacher (optional) — Einheit der Liegenschaft</span>
        <input className={`${inp} mb-1`} placeholder="Suche nach Einheit-Nr. oder Lage…"
               value={einheitSuche} onChange={e => setEinheitSuche(e.target.value)} disabled={!form.objekt_id} />
        <select className={inp} value={form.kostenverursacher_id} onChange={e => set('kostenverursacher_id', e.target.value)} disabled={!form.objekt_id}>
          <option value="">— kein Kostenverursacher —</option>
          {einheitenGefiltert.map(e => <option key={e.id} value={e.id}>{e.einheit_nr} — {e.lage}</option>)}
        </select>
      </div>

      {/* Skonto-Block */}
      <div className="mt-4 p-3 border rounded">
        <div className="text-sm font-medium text-gray-700 mb-2">Skonto</div>
        <div className="grid grid-cols-3 gap-4">
          {feldWrap('skonto_prozent', 'Prozent', (
            <input className={inp} value={form.skonto_prozent} onChange={e => set('skonto_prozent', e.target.value)} inputMode="decimal" />
          ))}
          <label className="block">
            <span className="text-xs text-gray-500 mb-1 block">Betrag</span>
            <input className={inp} value={form.skonto_betrag} onChange={e => set('skonto_betrag', e.target.value)} inputMode="decimal" />
          </label>
          <label className="block">
            <span className="text-xs text-gray-500 mb-1 block">Fällig bis</span>
            <input type="date" className={inp} value={form.skonto_faellig_bis} onChange={e => set('skonto_faellig_bis', e.target.value)} />
          </label>
        </div>
      </div>

      {/* Kennzeichen + Zahlweg */}
      <div className="flex flex-wrap items-center gap-6 mt-4">
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={form.ist_schlussrechnung} onChange={e => set('ist_schlussrechnung', e.target.checked)} />
          Schlussrechnung
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={form.ist_gutschrift} onChange={e => set('ist_gutschrift', e.target.checked)} />
          Gutschrift
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          Zahlweg:
          <select className="border rounded px-2 py-1 text-sm"
                  value={form.sepa_lastschrift ? 'lastschrift' : 'ueberweisung'}
                  onChange={e => set('sepa_lastschrift', e.target.value === 'lastschrift')}>
            <option value="ueberweisung">Überweisung</option>
            <option value="lastschrift">Lastschrift</option>
          </select>
        </label>
      </div>

      {/* Rechnung aufteilen (Splits) */}
      <div className="mt-4 p-3 border rounded">
        <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <input type="checkbox" checked={aufteilen} onChange={e => setAufteilen(e.target.checked)} disabled={!form.objekt_id} />
          Rechnung auf mehrere Aufwandskonten aufteilen
        </label>
        {aufteilen && (
          <div className="mt-3 space-y-2">
            {splits.map((row, i) => (
              <div key={i} className="grid grid-cols-[1fr_130px_28px] gap-2 items-center">
                <select className="border rounded px-2 py-1.5 text-sm" value={row.aufwandskonto}
                        onChange={e => setSplitRow(i, 'aufwandskonto', e.target.value)}>
                  <option value="">— Konto —</option>
                  {konten.map(k => <option key={k.id} value={k.id}>{k.kontonummer} — {k.kontoname}</option>)}
                </select>
                <input className="border rounded px-2 py-1.5 text-sm text-right" inputMode="decimal"
                       placeholder="0.00" value={row.betrag} onChange={e => setSplitRow(i, 'betrag', e.target.value)} />
                <button type="button" onClick={() => removeSplit(i)} disabled={splits.length <= 2}
                        className="text-gray-300 hover:text-red-400 disabled:opacity-30 text-lg">×</button>
              </div>
            ))}
            <div className="flex items-center justify-between text-xs pt-1">
              <button type="button" onClick={addSplit} className="text-blue-600 hover:underline">+ Zeile</button>
              <span className={splitPasst ? 'text-green-700' : 'text-orange-600'}>
                Summe {splitSumme.toFixed(2)} € von {brutto.toFixed(2)} € {splitPasst ? '✓' : ''}
              </span>
            </div>
          </div>
        )}
      </div>

      <label className="block mt-4">
        <span className="text-xs text-gray-500 mb-1 block">Leistungsbeschreibung</span>
        <textarea className={inp} rows={2} value={form.leistungsbeschreibung} onChange={e => set('leistungsbeschreibung', e.target.value)} />
      </label>

      {/* Aktionen */}
      <div className="flex items-center gap-3 mt-6">
        <button onClick={() => speichern('entwurf')} disabled={busy}
                className="px-3 py-2 text-sm rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-50">
          Entwurf speichern
        </button>
        <button onClick={() => speichern('zur_freigabe')} disabled={busy}
                className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
          Erfassen + zur Freigabe
        </button>
        <button onClick={() => speichern('freigeben')} disabled={busy || freigebenGesperrt}
                title={kritischRot ? 'Rotes kritisches Feld — bitte korrigieren' : hatGelb && !gelbGeprueft ? 'Gelbe Felder bitte bestätigen' : 'Betrag muss innerhalb Ihres Freigabelimits liegen'}
                className="px-4 py-2 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
          Erfassen + Freigeben
        </button>
      </div>
    </div>{/* Ende Formular-Bereich */}

    {/* PDF-Vorschau parallel */}
    {pdfUrl && (
      <div className="w-[45%] shrink-0 sticky top-0 h-screen border-l border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-white">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">PDF-Vorschau</span>
          {id && (
            <button onClick={() => rechnungenApi.openPdf(id).catch(() => {})}
                    className="text-xs text-blue-600 hover:underline">↗ In neuem Tab</button>
          )}
        </div>
        <iframe src={pdfUrl} className="w-full border-0" style={{ height: 'calc(100vh - 41px)' }} title="Rechnungs-PDF" />
      </div>
    )}
    </div>
  )
}
