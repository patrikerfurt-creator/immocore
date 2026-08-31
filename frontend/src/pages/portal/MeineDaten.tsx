import { FormEvent, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  bankverbindungSpeichern,
  emailAendern,
  ibanPruefen,
  kontaktSpeichern,
  meineDaten,
  PortalMeineDaten,
} from '../../api/portal'
import { Button } from '../../components/ui/Button'
import { IbanInput } from '../../components/ui/IbanInput'
import { Input } from '../../components/ui/Input'

/**
 * Eigene-Daten-Ansicht (Spec 1a, Kap. 6.2).
 *
 * Drei getrennte Sektionen mit eigenem Speichern-Button: ein Fehler in der
 * Bankverbindung darf das Speichern der Adresse nicht blockieren.
 *
 * Adresse ist ein mehrzeiliges Feld — ``Person.adresse`` ist im
 * Datenmodell ein einzelnes Textfeld, nicht Straße/PLZ/Ort getrennt.
 */
function fehlertext(fehler: unknown, ersatz: string): string {
  const detail = (fehler as { response?: { data?: { detail?: string; iban?: string[] } } })
    ?.response?.data
  return detail?.detail ?? detail?.iban?.[0] ?? ersatz
}

function Sektion({ titel, children }: { titel: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 shadow-sm">
      <header className="px-5 py-3 border-b border-gray-100">
        <h2 className="text-base font-semibold text-primary-900">{titel}</h2>
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

function KontaktSektion({ daten }: { daten: PortalMeineDaten }) {
  const queryClient = useQueryClient()
  const [strasse, setStrasse] = useState(daten.strasse)
  const [hausnummer, setHausnummer] = useState(daten.hausnummer)
  const [plz, setPlz] = useState(daten.plz)
  const [ort, setOrt] = useState(daten.ort)
  const [telefon, setTelefon] = useState(daten.telefon)
  const [meldung, setMeldung] = useState('')
  const [fehler, setFehler] = useState('')

  // Nach dem Speichern liefert der Server die maßgebliche Fassung zurück —
  // die Felder folgen ihr, statt einen lokalen Stand weiterzuführen.
  useEffect(() => {
    setStrasse(daten.strasse)
    setHausnummer(daten.hausnummer)
    setPlz(daten.plz)
    setOrt(daten.ort)
    setTelefon(daten.telefon)
  }, [daten.strasse, daten.hausnummer, daten.plz, daten.ort, daten.telefon])

  const mutation = useMutation({
    mutationFn: kontaktSpeichern,
    onSuccess: (neu) => {
      queryClient.setQueryData(['portal', 'meine-daten'], neu)
      setMeldung('Gespeichert.')
      setFehler('')
    },
    onError: (e) => {
      setFehler(fehlertext(e, 'Die Änderung konnte nicht gespeichert werden.'))
      setMeldung('')
    },
  })

  const plzUngueltig = plz.trim() !== '' && !/^\d{4,5}$/.test(plz.trim())

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setMeldung('')
    setFehler('')
    mutation.mutate({ strasse, hausnummer, plz, ort, telefon })
  }

  const unveraendert =
    strasse === daten.strasse && hausnummer === daten.hausnummer &&
    plz === daten.plz && ort === daten.ort && telefon === daten.telefon

  return (
    <Sektion titel="Adresse und Telefon">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* Straße breit, Hausnummer schmal — die übliche Aufteilung, damit
            das Formular nicht nach vier gleich wichtigen Feldern aussieht. */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className="sm:col-span-3">
            <Input label="Straße" value={strasse} onChange={e => setStrasse(e.target.value)} />
          </div>
          <Input
            label="Hausnummer"
            value={hausnummer}
            onChange={e => setHausnummer(e.target.value)}
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <Input
            label="PLZ"
            value={plz}
            onChange={e => setPlz(e.target.value)}
            inputMode="numeric"
            error={plzUngueltig ? 'Bitte 4 oder 5 Ziffern.' : undefined}
          />
          <div className="sm:col-span-3">
            <Input label="Ort" value={ort} onChange={e => setOrt(e.target.value)} />
          </div>
        </div>
        <Input
          label="Telefon"
          value={telefon}
          onChange={e => setTelefon(e.target.value)}
        />
        {meldung && <p className="text-sm text-green-700">{meldung}</p>}
        {fehler && <p className="text-sm text-red-600">{fehler}</p>}
        <div>
          <Button type="submit" disabled={mutation.isPending || unveraendert || plzUngueltig}>
            {mutation.isPending ? 'Wird gespeichert…' : 'Adresse und Telefon speichern'}
          </Button>
        </div>
      </form>
    </Sektion>
  )
}

function BankverbindungSektion({ daten }: { daten: PortalMeineDaten }) {
  const queryClient = useQueryClient()
  const [iban, setIban] = useState(daten.iban)
  const [bic, setBic] = useState(daten.bic)
  const [meldung, setMeldung] = useState('')
  const [fehler, setFehler] = useState('')

  useEffect(() => {
    setIban(daten.iban)
    setBic(daten.bic)
  }, [daten.iban, daten.bic])

  const mutation = useMutation({
    mutationFn: bankverbindungSpeichern,
    onSuccess: (neu) => {
      queryClient.setQueryData(['portal', 'meine-daten'], neu)
      setMeldung(
        neu.mandat_aktualisiert
          ? `Gespeichert. Ihr SEPA-Lastschriftmandat ${neu.mandatsreferenz} wurde mit der neuen Bankverbindung aktualisiert.`
          : 'Gespeichert.',
      )
      setFehler('')
    },
    onError: (e) => {
      setFehler(fehlertext(e, 'Die Bankverbindung konnte nicht gespeichert werden.'))
      setMeldung('')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setMeldung('')
    setFehler('')
    mutation.mutate({ iban, bic })
  }

  const unveraendert = iban === daten.iban && bic === daten.bic

  return (
    <Sektion titel="Bankverbindung">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* Transparenz-Hinweis (Spec Kap. 6.2): der Eigentümer soll wissen,
            dass die Änderung sein Lastschriftmandat mit umfasst. */}
        {daten.hat_aktives_mandat && (
          <p className="text-sm text-gray-600 bg-blue-50 border border-blue-100 rounded p-3">
            Für Sie besteht ein SEPA-Lastschriftmandat
            {daten.mandatsreferenz ? ` (${daten.mandatsreferenz})` : ''}.
            Eine Änderung der Bankverbindung gilt automatisch auch für dieses Mandat —
            künftige Hausgeldzahlungen werden dann von der neuen IBAN eingezogen.
          </p>
        )}
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">IBAN</label>
          {/* Prüft die Prüfsumme sofort im Browser und schlägt danach über
              den Portal-Endpunkt die Bank nach; die BIC wird dabei
              automatisch übernommen. Verbindlich geprüft wird beim
              Speichern erneut serverseitig. */}
          <IbanInput
            value={iban}
            onChange={setIban}
            pruefe={ibanPruefen}
            onBicFound={(gefundeneBic) => {
              if (daten.hat_aktives_mandat && !bic) setBic(gefundeneBic)
            }}
          />
        </div>
        <Input
          label="BIC (optional)"
          value={bic}
          onChange={e => setBic(e.target.value.toUpperCase())}
          disabled={!daten.hat_aktives_mandat}
        />
        {!daten.hat_aktives_mandat && (
          <p className="text-xs text-gray-500 -mt-2">
            Die BIC wird nur zusammen mit einem bestehenden Lastschriftmandat gespeichert.
          </p>
        )}
        {meldung && <p className="text-sm text-green-700">{meldung}</p>}
        {fehler && <p className="text-sm text-red-600">{fehler}</p>}
        <div>
          <Button type="submit" disabled={mutation.isPending || unveraendert}>
            {mutation.isPending ? 'Wird gespeichert…' : 'Bankverbindung speichern'}
          </Button>
        </div>
      </form>
    </Sektion>
  )
}

function EmailSektion({ daten }: { daten: PortalMeineDaten }) {
  const queryClient = useQueryClient()
  const [neueEmail, setNeueEmail] = useState('')
  const [meldung, setMeldung] = useState('')
  const [fehler, setFehler] = useState('')

  const mutation = useMutation({
    mutationFn: emailAendern,
    onSuccess: (antwort) => {
      setMeldung(antwort.detail)
      setFehler('')
      setNeueEmail('')
      queryClient.invalidateQueries({ queryKey: ['portal', 'meine-daten'] })
    },
    onError: (e) => {
      setFehler(fehlertext(e, 'Die E-Mail-Adresse konnte nicht geändert werden.'))
      setMeldung('')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setMeldung('')
    setFehler('')
    mutation.mutate(neueEmail)
  }

  return (
    <Sektion titel="E-Mail-Adresse">
      <div className="flex justify-between gap-4 pb-4 border-b border-gray-100">
        <span className="text-sm text-gray-500">Aktuell</span>
        <span className="text-sm font-medium text-gray-900">{daten.email || '—'}</span>
      </div>

      {daten.email_pending && (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-3 mt-4">
          Für <strong>{daten.email_pending}</strong> steht noch die Bestätigung aus.
          Bitte öffnen Sie den Link in dem an diese Adresse gesendeten Schreiben.
          Bis dahin melden Sie sich weiterhin mit Ihrer bisherigen Adresse an.
        </p>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-4">
        <Input
          label="Neue E-Mail-Adresse"
          type="email"
          value={neueEmail}
          onChange={e => setNeueEmail(e.target.value)}
          required
        />
        <p className="text-xs text-gray-500 -mt-2">
          Sie erhalten einen Bestätigungslink an die neue Adresse. Die Änderung wird
          erst danach wirksam — Ihre Anmeldung bleibt bis dahin unverändert möglich.
        </p>
        {meldung && <p className="text-sm text-green-700">{meldung}</p>}
        {fehler && <p className="text-sm text-red-600">{fehler}</p>}
        <div>
          <Button type="submit" variant="secondary" disabled={mutation.isPending || !neueEmail}>
            {mutation.isPending ? 'Wird gesendet…' : 'E-Mail-Adresse ändern'}
          </Button>
        </div>
      </form>
    </Sektion>
  )
}

export function MeineDaten() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['portal', 'meine-daten'],
    queryFn: meineDaten,
  })

  if (isLoading) return <p className="text-sm text-gray-500">Wird geladen…</p>
  if (isError || !data) {
    return <p className="text-sm text-red-600">Die Daten konnten nicht geladen werden.</p>
  }

  return (
    <div className="flex flex-col gap-5">
      <section className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-4">
        <h2 className="text-base font-semibold text-primary-900 mb-3">Stammdaten</h2>
        <dl className="divide-y divide-gray-100">
          <div className="flex justify-between gap-4 py-2">
            <dt className="text-sm text-gray-500">Name</dt>
            <dd className="text-sm font-medium text-gray-900">{data.name}</dd>
          </div>
          {data.personennummer && (
            <div className="flex justify-between gap-4 py-2">
              <dt className="text-sm text-gray-500">Kundennummer</dt>
              <dd className="text-sm font-medium text-gray-900">{data.personennummer}</dd>
            </div>
          )}
        </dl>
        <p className="text-xs text-gray-500 mt-3">
          Name und Kundennummer werden von der Hausverwaltung gepflegt. Wenden Sie sich
          bei einer Namensänderung bitte direkt an uns.
        </p>
      </section>

      <KontaktSektion daten={data} />
      <EmailSektion daten={data} />
      <BankverbindungSektion daten={data} />
    </div>
  )
}
