import { useEffect, useMemo, useState } from 'react'
import { isAxiosError } from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { briefboegenApi } from '../../api/korrespondenz'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { Briefbogen, BriefbogenPayload } from '../../types'
import { fehlerMeldung } from './konstanten'

/** Alle editierbaren Felder des Briefbogens (ohne id und die Logo-FKs). */
export type BriefbogenForm = Required<Omit<BriefbogenPayload, 'logo' | 'fuss_logo'>>

const inputCls =
  'w-full text-sm border border-gray-300 rounded px-2.5 py-1.5 focus:outline-none focus:border-primary-500 disabled:bg-gray-50 disabled:text-gray-600'

const REGISTER_HINWEIS =
  'Die Registerangaben (HRB-Nummer, Amtsgericht) stehen in zwei Feldern: in „Firmen-Fußzeile Zeile 1“ '
  + '(Fußzeile bei Nicht-WEG-Schreiben) und in „Pflichtangaben“ (Fußzeile bei WEG-Schreiben). '
  + 'Beide müssen konsistent gehalten werden — bei einer Änderung bitte beide Felder anpassen.'

export function istForbidden(error: unknown): boolean {
  return isAxiosError(error) && error.response?.status === 403
}

export function ausBriefbogen(b: Briefbogen): BriefbogenForm {
  return {
    bezeichnung: b.bezeichnung ?? '',
    firma_name: b.firma_name ?? '',
    firma_strasse: b.firma_strasse ?? '',
    firma_plz: b.firma_plz ?? '',
    firma_ort: b.firma_ort ?? '',
    telefon: b.telefon ?? '',
    email: b.email ?? '',
    web: b.web ?? '',
    sprechzeiten: b.sprechzeiten ?? '',
    hinweis_infoblock: b.hinweis_infoblock ?? '',
    fuss_firma_zeile1: b.fuss_firma_zeile1 ?? '',
    fuss_firma_zeile2: b.fuss_firma_zeile2 ?? '',
    fuss_firma_zeile3: b.fuss_firma_zeile3 ?? '',
    pflichtangaben: b.pflichtangaben ?? '',
    pflichtangaben_anzeigen: b.pflichtangaben_anzeigen,
    steuerzeichen_unsichtbar: b.steuerzeichen_unsichtbar ?? '',
    ist_standard: b.ist_standard,
    aktiv: b.aktiv,
  }
}

/** Pflichtfelder laut Modell (bezeichnung, firma_name); leer = gültig. */
export function validiereBriefbogen(f: BriefbogenForm): Partial<Record<keyof BriefbogenForm, string>> {
  const fehler: Partial<Record<keyof BriefbogenForm, string>> = {}
  if (f.bezeichnung.trim() === '') fehler.bezeichnung = 'Bezeichnung ist Pflicht.'
  if (f.firma_name.trim() === '') fehler.firma_name = 'Firmenname ist Pflicht.'
  return fehler
}

interface TextFeldProps {
  id: string
  label: string
  wert: string
  onChange: (v: string) => void
  disabled: boolean
  maxLength?: number
  fehler?: string
  hinweis?: string
  mehrzeilig?: boolean
  rows?: number
  mono?: boolean
}

function TextFeld({
  id, label, wert, onChange, disabled, maxLength, fehler, hinweis, mehrzeilig, rows = 4, mono,
}: TextFeldProps) {
  const cls = `${inputCls}${mono ? ' font-mono' : ''}`
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      {mehrzeilig ? (
        <textarea id={id} rows={rows} className={cls} value={wert} disabled={disabled}
          onChange={e => onChange(e.target.value)} />
      ) : (
        <input id={id} type="text" className={cls} value={wert} disabled={disabled}
          maxLength={maxLength} onChange={e => onChange(e.target.value)} />
      )}
      {hinweis && <p className="text-xs text-gray-500 mt-1">{hinweis}</p>}
      {fehler && <p role="alert" className="text-xs text-red-600 mt-1">{fehler}</p>}
    </div>
  )
}

function SchalterFeld({
  id, label, checked, onChange, disabled, hinweis,
}: {
  id: string; label: string; checked: boolean; onChange: (v: boolean) => void
  disabled: boolean; hinweis?: string
}) {
  return (
    <div>
      <label htmlFor={id} className="flex items-center gap-2 text-sm text-gray-700">
        <input id={id} type="checkbox" checked={checked} disabled={disabled}
          onChange={e => onChange(e.target.checked)} />
        {label}
      </label>
      {hinweis && <p className="text-xs text-gray-500 mt-1 ml-6">{hinweis}</p>}
    </div>
  )
}

function BriefbogenKarte({ briefbogen, andereStandards }: {
  briefbogen: Briefbogen
  /** Bezeichnungen anderer Briefbögen, die bereits Standard sind. */
  andereStandards: string[]
}) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<BriefbogenForm>(() => ausBriefbogen(briefbogen))
  const [fehler, setFehler] = useState<Partial<Record<keyof BriefbogenForm, string>>>({})
  const [saveFehler, setSaveFehler] = useState<string | null>(null)
  const [gespeichert, setGespeichert] = useState(false)

  // Nach Speichern/Neuladen den Formularstand an den Server-Stand angleichen.
  useEffect(() => {
    if (!editing) setForm(ausBriefbogen(briefbogen))
  }, [briefbogen, editing])

  const speichern = useMutation({
    mutationFn: (data: BriefbogenPayload) => briefboegenApi.update(briefbogen.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['korrespondenz-briefboegen'] })
      setEditing(false)
      setGespeichert(true)
    },
    onError: e => setSaveFehler(
      istForbidden(e)
        ? 'Kein Zugriff — Briefbögen dürfen nur Administratoren ändern.'
        : fehlerMeldung(e, 'Speichern fehlgeschlagen.'),
    ),
  })

  const setze = <K extends keyof BriefbogenForm>(k: K, v: BriefbogenForm[K]) =>
    setForm(p => ({ ...p, [k]: v }))

  const startEdit = () => {
    setForm(ausBriefbogen(briefbogen))
    setFehler({})
    setSaveFehler(null)
    setGespeichert(false)
    setEditing(true)
  }

  const abbrechen = () => {
    setForm(ausBriefbogen(briefbogen))
    setFehler({})
    setSaveFehler(null)
    setEditing(false)
  }

  const handleSave = () => {
    const f = validiereBriefbogen(form)
    setFehler(f)
    if (Object.keys(f).length > 0) return
    setSaveFehler(null)
    speichern.mutate(form)
  }

  const ro = !editing
  const doppelterStandard = form.ist_standard && andereStandards.length > 0

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5" data-testid="briefbogen-karte">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-gray-700">Briefbogen: {briefbogen.bezeichnung}</h2>
        {!editing && (
          <button type="button" onClick={startEdit} className="text-xs text-primary-600 hover:text-primary-800">
            Bearbeiten
          </button>
        )}
      </div>

      {gespeichert && !editing && (
        <p role="status" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-3">
          Briefbogen gespeichert.
        </p>
      )}

      <div className="space-y-6">
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Allgemein</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TextFeld id="bb-bezeichnung" label="Bezeichnung *" wert={form.bezeichnung} disabled={ro}
              maxLength={100} fehler={fehler.bezeichnung} onChange={v => setze('bezeichnung', v)} />
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-3">
            <SchalterFeld id="bb-aktiv" label="Aktiv" checked={form.aktiv} disabled={ro}
              onChange={v => setze('aktiv', v)} />
            <SchalterFeld id="bb-standard" label="Standard-Briefbogen" checked={form.ist_standard} disabled={ro}
              onChange={v => setze('ist_standard', v)}
              hinweis="Genau ein Briefbogen sollte Standard sein (wird verwendet, wenn die Vorlage keinen eigenen wählt)." />
          </div>
          {editing && doppelterStandard && (
            <p role="alert" className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              Achtung: Bereits Standard ist: {andereStandards.join(', ')}. Nach dem Speichern wären mehrere Briefbögen
              Standard — bitte den anderen Briefbogen zuerst auf „kein Standard“ setzen.
            </p>
          )}
        </section>

        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Absender</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TextFeld id="bb-firma-name" label="Firmenname *" wert={form.firma_name} disabled={ro}
              maxLength={200} fehler={fehler.firma_name} onChange={v => setze('firma_name', v)} />
            <TextFeld id="bb-firma-strasse" label="Straße" wert={form.firma_strasse} disabled={ro}
              maxLength={200} onChange={v => setze('firma_strasse', v)} />
            <TextFeld id="bb-firma-plz" label="PLZ" wert={form.firma_plz} disabled={ro}
              maxLength={10} onChange={v => setze('firma_plz', v)} />
            <TextFeld id="bb-firma-ort" label="Ort" wert={form.firma_ort} disabled={ro}
              maxLength={100} onChange={v => setze('firma_ort', v)} />
          </div>
        </section>

        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Infoblock</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <TextFeld id="bb-telefon" label="Telefon" wert={form.telefon} disabled={ro}
              maxLength={50} onChange={v => setze('telefon', v)} />
            <TextFeld id="bb-email" label="E-Mail" wert={form.email} disabled={ro}
              maxLength={200} onChange={v => setze('email', v)} />
            <TextFeld id="bb-web" label="Web" wert={form.web} disabled={ro}
              maxLength={200} onChange={v => setze('web', v)} />
          </div>
          <TextFeld id="bb-sprechzeiten" label="Sprechzeiten" wert={form.sprechzeiten} disabled={ro}
            mehrzeilig rows={5} mono onChange={v => setze('sprechzeiten', v)}
            hinweis="Eine Zeile je Eintrag; Tag und Zeit durch einen Tabulator getrennt (z. B. „Mo–Do⇥9–16 Uhr“)." />
          <TextFeld id="bb-hinweis" label="Hinweis im Infoblock" wert={form.hinweis_infoblock} disabled={ro}
            mehrzeilig rows={3} onChange={v => setze('hinweis_infoblock', v)} />
        </section>

        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Fußzeilen und Registerangaben</h3>
          <p role="note" className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            {REGISTER_HINWEIS}
          </p>
          <div className="rounded border border-gray-200 p-4 space-y-3">
            <h4 className="text-sm font-medium text-gray-700">Fußzeile bei Nicht-WEG-Schreiben (Firmen-Fußzeile)</h4>
            <TextFeld id="bb-fuss1" label="Firmen-Fußzeile Zeile 1 (enthält HRB/Amtsgericht)"
              wert={form.fuss_firma_zeile1} disabled={ro} maxLength={200}
              onChange={v => setze('fuss_firma_zeile1', v)}
              hinweis="Registerangabe, nur in Nicht-WEG-Schreiben. Muss zu den „Pflichtangaben“ unten passen." />
            <TextFeld id="bb-fuss2" label="Firmen-Fußzeile Zeile 2" wert={form.fuss_firma_zeile2}
              disabled={ro} maxLength={200} onChange={v => setze('fuss_firma_zeile2', v)} />
            <TextFeld id="bb-fuss3" label="Firmen-Fußzeile Zeile 3" wert={form.fuss_firma_zeile3}
              disabled={ro} maxLength={200} onChange={v => setze('fuss_firma_zeile3', v)} />
          </div>
          <div className="rounded border border-gray-200 p-4 space-y-3">
            <h4 className="text-sm font-medium text-gray-700">Fußzeile bei WEG-Schreiben (Pflichtangaben)</h4>
            <TextFeld id="bb-pflicht" label="Pflichtangaben (enthält HRB/Amtsgericht)"
              wert={form.pflichtangaben} disabled={ro} mehrzeilig rows={3}
              onChange={v => setze('pflichtangaben', v)}
              hinweis="GmbH-Pflichtangaben (§ 35a GmbHG), 6-pt-Zeile unter der WEG-Bankverbindung. Registerangabe muss zu „Firmen-Fußzeile Zeile 1“ oben passen." />
            <SchalterFeld id="bb-pflicht-anzeigen" label="Pflichtangaben in der WEG-Fußzeile anzeigen"
              checked={form.pflichtangaben_anzeigen} disabled={ro}
              onChange={v => setze('pflichtangaben_anzeigen', v)} />
          </div>
        </section>

        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Weiteres</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TextFeld id="bb-steuerzeichen" label="Unsichtbares Steuerzeichen"
              wert={form.steuerzeichen_unsichtbar} disabled={ro} maxLength={50} mono
              onChange={v => setze('steuerzeichen_unsichtbar', v)} />
          </div>
          <div className="text-xs text-gray-500" data-testid="briefbogen-logo-info">
            <p>Logo (Kopf): {briefbogen.logo ? `Dokument ${briefbogen.logo}` : 'nicht hinterlegt'}</p>
            <p>Logo (Fußzeile): {briefbogen.fuss_logo ? `Dokument ${briefbogen.fuss_logo}` : 'nicht hinterlegt'}</p>
            <p className="mt-1">Die Logo-Verknüpfung wird hier nur angezeigt; Hochladen und Ändern ist noch nicht möglich.</p>
          </div>
        </section>

        {saveFehler && <p role="alert" className="text-sm text-red-600">{saveFehler}</p>}

        {editing && (
          <div className="flex gap-2">
            <Button type="button" onClick={handleSave} disabled={speichern.isPending}>
              {speichern.isPending ? 'Speichert…' : 'Speichern'}
            </Button>
            <Button type="button" variant="ghost" onClick={abbrechen} disabled={speichern.isPending}>
              Abbrechen
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

export function BriefbogenVerwaltung() {
  const [auswahl, setAuswahl] = useState<string | null>(null)

  const { data: liste, isLoading, error } = useQuery({
    queryKey: ['korrespondenz-briefboegen'],
    queryFn: () => briefboegenApi.list(),
    retry: false,
  })

  const gewaehlt = useMemo(() => {
    if (!liste || liste.length === 0) return null
    return liste.find(b => b.id === auswahl) ?? liste[0]
  }, [liste, auswahl])

  const standards = (liste ?? []).filter(b => b.ist_standard)
  const verboten = istForbidden(error)

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold">Briefbögen</h1>

      {isLoading && <p className="text-gray-400">Lade Briefbögen…</p>}

      {verboten && (
        <p role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
          Kein Zugriff — diese Seite ist nur für Administratoren verfügbar.
        </p>
      )}
      {error && !verboten && (
        <p role="alert" className="text-red-600">Briefbögen konnten nicht geladen werden.</p>
      )}

      {liste && liste.length === 0 && <p className="text-gray-400">Keine Briefbögen vorhanden.</p>}

      {liste && liste.length > 0 && (
        <>
          {standards.length !== 1 && (
            <p role="alert" className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              {standards.length === 0
                ? 'Es ist kein Briefbogen als Standard markiert.'
                : `Es sind ${standards.length} Briefbögen als Standard markiert — genau einer sollte Standard sein.`}
            </p>
          )}

          <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-3 py-2">Bezeichnung</th>
                  <th className="px-3 py-2">Firma</th>
                  <th className="px-3 py-2">Standard</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {liste.map(b => (
                  <tr key={b.id}
                    className={`border-t border-gray-100 ${gewaehlt?.id === b.id ? 'bg-primary-50' : 'hover:bg-gray-50'}`}>
                    <td className="px-3 py-2">{b.bezeichnung}</td>
                    <td className="px-3 py-2">{b.firma_name}</td>
                    <td className="px-3 py-2">{b.ist_standard ? 'Ja' : '–'}</td>
                    <td className="px-3 py-2">
                      <Badge value={b.aktiv ? 'aktiv' : 'archiviert'} label={b.aktiv ? 'Aktiv' : 'Inaktiv'} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button type="button" onClick={() => setAuswahl(b.id)}
                        aria-label={`Briefbogen ${b.bezeichnung} auswählen`}
                        className="text-xs text-primary-600 hover:text-primary-800">
                        Auswählen
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {gewaehlt && (
            <BriefbogenKarte
              key={gewaehlt.id}
              briefbogen={gewaehlt}
              andereStandards={standards.filter(b => b.id !== gewaehlt.id).map(b => b.bezeichnung)}
            />
          )}
        </>
      )}
    </div>
  )
}
