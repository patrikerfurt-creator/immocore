import { useEffect, useState } from 'react'
import { objekteApi } from '../../api/objekte'
import type { MahnEinstellung } from '../../types'

interface FormState {
  mahngebuehr: string
  anzahl_mahnstufen: string
  zinsen_erheben: boolean
}

const LEER: FormState = { mahngebuehr: '', anzahl_mahnstufen: '2', zinsen_erheben: false }

const inputCls =
  'w-full text-sm border border-gray-300 rounded px-2.5 py-1.5 focus:outline-none focus:border-primary-500'

function istNotFound(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 404
}

function ausEinstellung(e: MahnEinstellung): FormState {
  return {
    mahngebuehr: String(e.mahngebuehr).replace('.', ','),
    anzahl_mahnstufen: String(e.anzahl_mahnstufen),
    zinsen_erheben: e.zinsen_erheben,
  }
}

/** Validiert das Formular; liefert Fehlertexte je Feld (leer = gültig). */
export function validiereMahnEinstellung(f: FormState): Partial<Record<keyof FormState, string>> {
  const fehler: Partial<Record<keyof FormState, string>> = {}
  const betrag = f.mahngebuehr.trim().replace(',', '.')
  if (betrag === '') {
    fehler.mahngebuehr = 'Mahngebühr ist Pflicht.'
  } else if (!/^\d+(\.\d{1,2})?$/.test(betrag)) {
    fehler.mahngebuehr = 'Mahngebühr muss ein Betrag >= 0 mit höchstens 2 Nachkommastellen sein.'
  }
  if (f.anzahl_mahnstufen !== '1' && f.anzahl_mahnstufen !== '2') {
    fehler.anzahl_mahnstufen = 'Anzahl Mahnstufen muss 1 oder 2 sein.'
  }
  return fehler
}

function serverFehler(err: unknown): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data
  if (data && typeof data === 'object') {
    const teile = Object.values(data as Record<string, unknown>)
      .flat()
      .filter(v => typeof v === 'string')
    if (teile.length > 0) return teile.join(' ')
  }
  return 'Speichern fehlgeschlagen.'
}

export function MahnEinstellungSection({ objektId }: { objektId: string }) {
  const [laden, setLaden] = useState(true)
  const [ladefehler, setLadefehler] = useState<string | null>(null)
  const [gespeichert, setGespeichert] = useState<MahnEinstellung | null>(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<FormState>(LEER)
  const [fehler, setFehler] = useState<Partial<Record<keyof FormState, string>>>({})
  const [saving, setSaving] = useState(false)
  const [saveFehler, setSaveFehler] = useState<string | null>(null)

  useEffect(() => {
    let aktiv = true
    setLaden(true)
    setLadefehler(null)
    objekteApi
      .getMahnEinstellung(objektId)
      .then(e => { if (aktiv) setGespeichert(e) })
      .catch(err => {
        if (!aktiv) return
        if (istNotFound(err)) setGespeichert(null)
        else setLadefehler('Mahn-Konfiguration konnte nicht geladen werden.')
      })
      .finally(() => { if (aktiv) setLaden(false) })
    return () => { aktiv = false }
  }, [objektId])

  const startEdit = () => {
    setForm(gespeichert ? ausEinstellung(gespeichert) : LEER)
    setFehler({})
    setSaveFehler(null)
    setEditing(true)
  }

  const handleSave = async () => {
    const f = validiereMahnEinstellung(form)
    setFehler(f)
    if (Object.keys(f).length > 0) return
    setSaving(true)
    setSaveFehler(null)
    try {
      const neu = await objekteApi.putMahnEinstellung(objektId, {
        mahngebuehr: form.mahngebuehr.trim().replace(',', '.'),
        anzahl_mahnstufen: Number(form.anzahl_mahnstufen) as 1 | 2,
        zinsen_erheben: form.zinsen_erheben,
      })
      setGespeichert(neu)
      setEditing(false)
    } catch (err) {
      setSaveFehler(serverFehler(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4" data-testid="mahn-einstellung">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-gray-700">Mahnwesen</h2>
        {!editing && !laden && !ladefehler && (
          <button onClick={startEdit} className="text-xs text-primary-600 hover:text-primary-800">
            Bearbeiten
          </button>
        )}
      </div>

      {laden ? (
        <p className="text-sm text-gray-400">Lädt…</p>
      ) : ladefehler ? (
        <p className="text-sm text-red-600">{ladefehler}</p>
      ) : (
        <>
          {!gespeichert && (
            <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-3">
              Noch nicht konfiguriert. Ohne Mahn-Konfiguration ist der Mahnlauf für dieses Objekt gesperrt.
            </p>
          )}

          {editing ? (
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label htmlFor="mahn-gebuehr" className="block text-xs font-medium text-gray-600 mb-1">
                    Mahngebühr (€) *
                  </label>
                  <input
                    id="mahn-gebuehr"
                    type="text"
                    inputMode="decimal"
                    className={inputCls}
                    value={form.mahngebuehr}
                    onChange={e => setForm(p => ({ ...p, mahngebuehr: e.target.value }))}
                    placeholder="z. B. 5,00"
                  />
                  {fehler.mahngebuehr && <p className="text-xs text-red-600 mt-1">{fehler.mahngebuehr}</p>}
                </div>
                <div>
                  <label htmlFor="mahn-stufen" className="block text-xs font-medium text-gray-600 mb-1">
                    Anzahl Mahnstufen
                  </label>
                  <select
                    id="mahn-stufen"
                    className={inputCls}
                    value={form.anzahl_mahnstufen}
                    onChange={e => setForm(p => ({ ...p, anzahl_mahnstufen: e.target.value }))}
                  >
                    <option value="1">1</option>
                    <option value="2">2</option>
                  </select>
                  {fehler.anzahl_mahnstufen && (
                    <p className="text-xs text-red-600 mt-1">{fehler.anzahl_mahnstufen}</p>
                  )}
                </div>
                <div>
                  <label htmlFor="mahn-zinsen" className="block text-xs font-medium text-gray-600 mb-1">
                    Zinsen erheben
                  </label>
                  <select
                    id="mahn-zinsen"
                    className={inputCls}
                    value={form.zinsen_erheben ? 'ja' : 'nein'}
                    onChange={e => setForm(p => ({ ...p, zinsen_erheben: e.target.value === 'ja' }))}
                  >
                    <option value="ja">Ja</option>
                    <option value="nein">Nein</option>
                  </select>
                </div>
              </div>

              <p className="text-xs text-gray-500">
                Ohne Mahn-Konfiguration ist der Mahnlauf für dieses Objekt gesperrt.
              </p>

              {saveFehler && <p className="text-sm text-red-600">{saveFehler}</p>}

              <div className="flex gap-2">
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-1.5 rounded bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
                >
                  {saving ? 'Speichert…' : 'Speichern'}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5"
                >
                  Abbrechen
                </button>
              </div>
            </div>
          ) : gespeichert ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col">
                <span className="text-xs text-gray-400">Mahngebühr</span>
                <span className="text-sm text-gray-800">
                  {parseFloat(gespeichert.mahngebuehr).toLocaleString('de-DE', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })} €
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs text-gray-400">Anzahl Mahnstufen</span>
                <span className="text-sm text-gray-800">{gespeichert.anzahl_mahnstufen}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs text-gray-400">Zinsen erheben</span>
                <span className="text-sm text-gray-800">{gespeichert.zinsen_erheben ? 'Ja' : 'Nein'}</span>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
