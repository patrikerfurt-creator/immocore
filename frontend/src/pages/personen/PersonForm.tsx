import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { IbanInput } from '../../components/ui/IbanInput'
import { personenApi } from '../../api/personen'
import type { Person } from '../../types'

const ANREDE_WERTE = ['', 'Herr', 'Frau', 'Eheleute', 'Herren', 'Damen', 'Herr und Frau', 'Firma'] as const
const PERSON_TYP_OPTIONEN = [
  { value: '100', label: 'Eigentümer' },
  { value: '200', label: 'Mieter' },
  { value: '300', label: 'Kreditor' },
  { value: '400', label: 'Sonstiges' },
]

interface Props {
  person?: Person
}

const PAAR_ANREDEN = new Set(['Eheleute', 'Herren', 'Damen', 'Herr und Frau'])

const PAAR_EINZEL: Record<string, [string, string]> = {
  'Eheleute':      ['Frau',  'Herr'],
  'Herren':        ['Herr',  'Herr'],
  'Damen':         ['Frau',  'Frau'],
  'Herr und Frau': ['Frau',  'Herr'],
}

function briefanredeZeile(einzelAnrede: string, name: string, gross: boolean): string {
  const prefix = gross ? 'Sehr' : 'sehr'
  const endung = einzelAnrede === 'Herr' ? 'er' : 'e'
  return `${prefix} geehrt${endung} ${einzelAnrede} ${name},`
}

function autoBriefanreden(
  anrede: string,
  nachname: string,
  nachname2: string,
  istFirma: boolean,
): [string, string] {
  if (istFirma || anrede === 'Firma') return ['Sehr geehrte Damen und Herren,', '']

  const paar = PAAR_EINZEL[anrede]
  if (paar) {
    const [a1, a2] = paar
    const n1 = nachname.trim()
    const n2 = nachname2.trim() || nachname.trim()
    return [briefanredeZeile(a1, n1, true), briefanredeZeile(a2, n2, false)]
  }
  if (anrede === 'Herr') return [briefanredeZeile('Herr', nachname.trim(), true), '']
  if (anrede === 'Frau') return [briefanredeZeile('Frau', nachname.trim(), true), '']
  return ['', '']
}

interface FormState {
  person_typ: string
  anrede: string
  ist_firma: boolean
  firmenname: string
  vorname: string
  nachname: string
  vorname2: string
  nachname2: string
  email: string
  telefon: string
  adresse: string
  ibans: string[]
  briefanrede: string
  briefanrede2: string
}

function toFormState(p?: Person): FormState {
  return {
    person_typ: (p as unknown as Record<string, string>)?.person_typ ?? '100',
    anrede: (p as unknown as Record<string, string>)?.anrede ?? '',
    ist_firma: p?.ist_firma ?? false,
    firmenname: p?.firmenname ?? '',
    vorname: p?.vorname ?? '',
    nachname: p?.nachname ?? '',
    vorname2: p?.vorname2 ?? '',
    nachname2: p?.nachname2 ?? '',
    email: p?.email ?? '',
    telefon: p?.telefon ?? '',
    adresse: (p as unknown as Record<string, string>)?.adresse ?? '',
    ibans: p?.ibans ?? [''],
    briefanrede:  (p as unknown as Record<string, string>)?.briefanrede  ?? '',
    briefanrede2: (p as unknown as Record<string, string>)?.briefanrede2 ?? '',
  }
}

export function PersonForm({ person }: Props) {
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>(() => toFormState(person))
  const [briefanredeManual, setBriefanredeManual] = useState(
    !!(person && (person as unknown as Record<string, string>).briefanrede)
  )
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])

  const AUTO_FELDER = new Set(['anrede', 'nachname', 'nachname2', 'firmenname', 'ist_firma'])

  const set = <K extends keyof FormState>(field: K, value: FormState[K]) =>
    setForm(prev => {
      const next = { ...prev, [field]: value }
      if (!briefanredeManual && AUTO_FELDER.has(field as string)) {
        const [ba1, ba2] = autoBriefanreden(
          field === 'anrede'    ? (value as string)  : prev.anrede,
          field === 'nachname'  ? (value as string)  : prev.nachname,
          field === 'nachname2' ? (value as string)  : prev.nachname2,
          field === 'ist_firma' ? (value as boolean) : prev.ist_firma,
        )
        next.briefanrede  = ba1
        next.briefanrede2 = ba2
      }
      return next
    })

  const updateIban = (idx: number, val: string) =>
    set('ibans', form.ibans.map((v, i) => i === idx ? val : v))

  const addIban = () => set('ibans', [...form.ibans, ''])
  const removeIban = (idx: number) => set('ibans', form.ibans.filter((_, i) => i !== idx))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrors([])
    setSaving(true)
    const payload = {
      ...form,
      ibans: form.ibans.map(v => v.replace(/\s/g, '').toUpperCase()).filter(Boolean),
    }
    try {
      if (person) {
        await personenApi.update(person.id, payload)
        navigate(`/personen/${person.id}`)
      } else {
        const neu = await personenApi.create(payload)
        navigate(`/personen/${neu.id}`)
      }
    } catch (err: unknown) {
      const data = (err as { response?: { data?: Record<string, string[]> } })?.response?.data
      if (data) {
        setErrors(Object.entries(data).flatMap(([k, v]) => v.map((msg: string) => `${k}: ${msg}`)))
      } else {
        setErrors(['Speichern fehlgeschlagen.'])
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      {/* Typ & Anrede */}
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Person-Typ *</label>
          <select
            value={form.person_typ}
            onChange={e => set('person_typ', e.target.value)}
            required
            className="rounded border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
          >
            {PERSON_TYP_OPTIONEN.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Anrede</label>
          <select
            value={form.anrede}
            onChange={e => set('anrede', e.target.value)}
            className="rounded border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
          >
            {ANREDE_WERTE.map(a => (
              <option key={a} value={a}>{a === '' ? '–' : a}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Firma-Toggle */}
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="ist_firma"
          checked={form.ist_firma}
          onChange={e => set('ist_firma', e.target.checked)}
          className="accent-primary-600"
        />
        <label htmlFor="ist_firma" className="text-sm text-gray-700">Juristische Person / Firma</label>
      </div>

      {/* Name */}
      {form.ist_firma ? (
        <Input
          label="Firmenname *"
          value={form.firmenname}
          onChange={e => set('firmenname', e.target.value)}
          placeholder="Musterfirma GmbH"
          required
        />
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label={PAAR_ANREDEN.has(form.anrede) ? 'Vorname 1 *' : 'Vorname *'}
              value={form.vorname}
              onChange={e => set('vorname', e.target.value)}
              placeholder="Klaus"
              required
            />
            <Input
              label={PAAR_ANREDEN.has(form.anrede) ? 'Nachname 1 *' : 'Nachname *'}
              value={form.nachname}
              onChange={e => set('nachname', e.target.value)}
              placeholder="Müller"
              required
            />
          </div>
          {PAAR_ANREDEN.has(form.anrede) && (
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Vorname 2"
                value={form.vorname2}
                onChange={e => set('vorname2', e.target.value)}
                placeholder="Maria"
              />
              <Input
                label="Nachname 2"
                value={form.nachname2}
                onChange={e => set('nachname2', e.target.value)}
                placeholder="Müller"
              />
            </div>
          )}
        </div>
      )}

      {/* Briefanrede */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-700">
            Briefanrede{PAAR_EINZEL[form.anrede] ? ' 1' : ''}
          </label>
          {briefanredeManual && (
            <button
              type="button"
              onClick={() => {
                setBriefanredeManual(false)
                const [ba1, ba2] = autoBriefanreden(
                  form.anrede, form.nachname, form.nachname2, form.ist_firma
                )
                setForm(prev => ({ ...prev, briefanrede: ba1, briefanrede2: ba2 }))
              }}
              className="text-xs text-primary-600 hover:text-primary-700 underline"
            >
              Automatisch zurücksetzen
            </button>
          )}
        </div>
        <input
          type="text"
          value={form.briefanrede}
          onChange={e => {
            setBriefanredeManual(true)
            setForm(prev => ({ ...prev, briefanrede: e.target.value }))
          }}
          placeholder="Sehr geehrter Herr Mustermann,"
          className="rounded border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
        />

        {PAAR_EINZEL[form.anrede] && (
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Briefanrede 2</label>
            <input
              type="text"
              value={form.briefanrede2}
              onChange={e => {
                setBriefanredeManual(true)
                setForm(prev => ({ ...prev, briefanrede2: e.target.value }))
              }}
              placeholder="sehr geehrter Herr Mustermann,"
              className="rounded border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
          </div>
        )}

        <p className="text-xs text-gray-400">
          Wird automatisch aus Anrede und Nachname befüllt. Manuell änderbar.
        </p>
      </div>

      {/* Kontakt */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="E-Mail"
          type="email"
          value={form.email}
          onChange={e => set('email', e.target.value)}
          placeholder="k.mueller@email.de"
        />
        <Input
          label="Telefon"
          type="tel"
          value={form.telefon}
          onChange={e => set('telefon', e.target.value)}
          placeholder="+49 69 123456"
        />
      </div>

      {/* Adresse */}
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">Adresse</label>
        <textarea
          value={form.adresse}
          onChange={e => set('adresse', e.target.value)}
          rows={3}
          placeholder={'Musterstraße 1\n60001 Frankfurt'}
          className="rounded border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none resize-none"
        />
      </div>

      {/* IBANs */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700">IBANs</label>
        {form.ibans.map((iban, idx) => (
          <div key={idx} className="flex gap-2">
            <IbanInput
              value={iban}
              onChange={v => updateIban(idx, v)}
              className="flex-1"
            />
            {form.ibans.length > 1 && (
              <button
                type="button"
                onClick={() => removeIban(idx)}
                className="text-gray-300 hover:text-red-500 transition-colors text-lg leading-none px-1"
              >
                ×
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={addIban}
          className="text-sm text-primary-600 hover:text-primary-700 font-medium"
        >
          + Weitere IBAN
        </button>
      </div>

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
        </div>
      )}

      <div className="flex gap-3">
        <Button type="submit" disabled={saving}>
          {saving ? 'Speichern…' : person ? 'Änderungen speichern' : 'Person anlegen'}
        </Button>
        <Button type="button" variant="secondary" onClick={() => navigate('/personen')}>
          Abbrechen
        </Button>
      </div>
    </form>
  )
}
