import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import { wirtschaftsjahreApi } from '../../api/wirtschaftsjahre'
import { useObjektStore } from '../../stores/objekt'
import { Button } from '../../components/ui/Button'
import type { Konto, Buchungsart, Wirtschaftsjahr } from '../../types'

const EUR = (v: number | string) =>
  Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
const DATUM = (s: string) => new Date(s).toLocaleDateString('de-DE')

function today() {
  return new Date().toISOString().slice(0, 10)
}

interface FormState {
  buchungsart: string
  buchungsdatum: string
  belegnr: string
  buchungstext: string
  betrag: string
  soll_konto: string
  haben_konto: string
}

interface ZeFormState {
  personenkonto_id: string
  bank_sachkonto_id: string
  betrag: string
  buchungsdatum: string
  buchungstext: string
}

const EMPTY: FormState = {
  buchungsart: '',
  buchungsdatum: today(),
  belegnr: '',
  buchungstext: '',
  betrag: '',
  soll_konto: '',
  haben_konto: '',
}

const ZE_EMPTY: ZeFormState = {
  personenkonto_id: '',
  bank_sachkonto_id: '',
  betrag: '',
  buchungsdatum: today(),
  buchungstext: '',
}

export function Dialogbuchhaltung() {
  const objektId = useObjektStore(s => s.selectedId)
  const qc = useQueryClient()
  const [modus, setModus] = useState<'sachkonto' | 'personenkonto' | 'kreditor'>('sachkonto')
  const [form, setForm] = useState<FormState>(EMPTY)
  const [zeForm, setZeForm] = useState<ZeFormState>(ZE_EMPTY)
  const [success, setSuccess] = useState(false)
  const [zeSuccess, setZeSuccess] = useState(false)
  const [aktuellerStapelId, setAktuellerStapelId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [selectedWjId, setSelectedWjId] = useState<string | null>(null)

  const { data: offeneStapel } = useQuery({
    queryKey: ['buchungsstapel', objektId, 'offen'],
    queryFn: () => buchhaltungApi.stapelListe({ objekt: objektId!, status: 'offen' }),
    enabled: !!objektId,
    select: (data: { id: string; bezeichnung: string; anzahl_buchungen: number; gesamt_summe: number }[]) => data,
  })

  const aktuellerStapel = offeneStapel?.find((s: { id: string }) => s.id === aktuellerStapelId)
    ?? (aktuellerStapelId ? null : offeneStapel?.[0] ?? null)

  const stapelAnlegenMut = useMutation({
    mutationFn: () => buchhaltungApi.stapelAnlegen(objektId!),
    onSuccess: (stapel: { id: string }) => {
      setAktuellerStapelId(stapel.id)
      qc.invalidateQueries({ queryKey: ['buchungsstapel', objektId] })
    },
  })

  const ausbuchenMut = useMutation({
    mutationFn: (stapelId: string) => buchhaltungApi.stapelAusbuchen(stapelId),
    onSuccess: () => {
      setAktuellerStapelId(null)
      invalidateAll()
      qc.invalidateQueries({ queryKey: ['buchungen'] })
    },
  })

  const { data: buchungsarten } = useQuery({
    queryKey: ['buchungsarten-manuell', modus],
    queryFn: () => buchhaltungApi.buchungsartenManuell(modus),
    enabled: !!objektId,
  })

  const { data: wirtschaftsjahre } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => wirtschaftsjahreApi.list({ objekt: objektId! }),
    enabled: !!objektId,
    select: (wjs: Wirtschaftsjahr[]) => [...wjs].sort((a, b) => b.jahr - a.jahr),
  })

  // Aktives WJ: zuerst selectedWjId, dann das neueste offene, dann das neueste gesamt
  const aktivesWj: Wirtschaftsjahr | undefined = (() => {
    if (!wirtschaftsjahre?.length) return undefined
    if (selectedWjId) return wirtschaftsjahre.find(w => w.id === selectedWjId)
    return (
      wirtschaftsjahre.find(w => w.status === 'offen') ??
      wirtschaftsjahre[0]
    )
  })()

  const { data: konten } = useQuery({
    queryKey: ['konten', objektId, aktivesWj?.id],
    queryFn: () =>
      buchhaltungApi.konten(objektId!, aktivesWj ? { wirtschaftsjahr: aktivesWj.id } : undefined),
    enabled: !!objektId,
  })

  const { data: letzteZehn } = useQuery({
    queryKey: ['buchungen-dialog', objektId],
    queryFn: () =>
      buchhaltungApi.buchungen(
        objektId ? { objekt: objektId, limit: '10' } : {}
      ),
    enabled: !!objektId,
  })

  const { data: personenkonten } = useQuery({
    queryKey: ['personenkonten-saldo', objektId],
    queryFn: () => buchhaltungApi.personenkontenMitSaldo(objektId!),
    enabled: !!objektId,
  })

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['buchungen-dialog', objektId] })
    qc.invalidateQueries({ queryKey: ['buchungen'] })
    qc.invalidateQueries({ queryKey: ['buchungsstapel', objektId] })
    qc.invalidateQueries({ queryKey: ['personenkonten-saldo', objektId] })
  }

  const buchenMut = useMutation({
    mutationFn: async () => {
      let stapelId = aktuellerStapel?.id ?? null
      if (!stapelId) {
        const neuerStapel = await buchhaltungApi.stapelAnlegen(objektId!) as { id: string }
        stapelId = neuerStapel.id
        setAktuellerStapelId(stapelId)
      }
      return buchhaltungApi.createBuchung({
        objekt: objektId!,
        wirtschaftsjahr: aktivesWj?.id ?? undefined,
        buchungsart: form.buchungsart || undefined,
        buchungsdatum: form.buchungsdatum,
        belegnr: form.belegnr,
        buchungstext: form.buchungstext,
        betrag: form.betrag as unknown as number,
        soll_konto: form.soll_konto || undefined,
        haben_konto: form.haben_konto || undefined,
        stapel: stapelId,
      } as never)
    },
    onSuccess: () => {
      invalidateAll()
      setForm({ ...EMPTY, buchungsdatum: form.buchungsdatum })
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    },
  })

  const aktualisierenMut = useMutation({
    mutationFn: () =>
      buchhaltungApi.updateBuchung(editingId!, {
        buchungsart: form.buchungsart || undefined,
        buchungsdatum: form.buchungsdatum,
        belegnr: form.belegnr,
        buchungstext: form.buchungstext,
        betrag: form.betrag as unknown as number,
        soll_konto: form.soll_konto || undefined,
        haben_konto: form.haben_konto || undefined,
      } as never),
    onSuccess: () => {
      invalidateAll()
      setEditingId(null)
      setForm(EMPTY)
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    },
  })

  const zeMut = useMutation({
    mutationFn: () =>
      buchhaltungApi.zahlungseingang(zeForm.personenkonto_id, {
        bank_sachkonto_id: zeForm.bank_sachkonto_id,
        betrag: Number(zeForm.betrag),
        buchungsdatum: zeForm.buchungsdatum,
        buchungstext: zeForm.buchungstext || undefined,
        wirtschaftsjahr_id: aktivesWj?.id,
      }),
    onSuccess: () => {
      invalidateAll()
      setZeForm({ ...ZE_EMPTY, buchungsdatum: zeForm.buchungsdatum })
      setZeSuccess(true)
      setTimeout(() => setZeSuccess(false), 4000)
    },
  })

  const setZe = (field: keyof ZeFormState) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => setZeForm(prev => ({ ...prev, [field]: e.target.value }))

  const kannZeBuchen =
    !!zeForm.personenkonto_id &&
    !!zeForm.bank_sachkonto_id &&
    !!zeForm.betrag &&
    Number(zeForm.betrag) > 0 &&
    !!zeForm.buchungsdatum

  function handleEditClick(buchungId: string) {
    buchhaltungApi.getBuchung(buchungId).then((b) => {
      setEditingId(buchungId)
      setForm({
        buchungsart: (b.buchungsart as string) ?? '',
        buchungsdatum: (b.buchungsdatum as string) ?? today(),
        belegnr: (b.belegnr as string) ?? '',
        buchungstext: (b.buchungstext as string) ?? '',
        betrag: String(b.betrag ?? ''),
        soll_konto: (b.soll_konto as string) ?? '',
        haben_konto: (b.haben_konto as string) ?? '',
      })
    })
  }

  function handleEditAbbrechen() {
    setEditingId(null)
    setForm(EMPTY)
  }

const set = (field: keyof FormState) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => setForm(prev => ({ ...prev, [field]: e.target.value }))

  const aktiveKonten = (konten ?? []).filter(
    (k: Konto) => k.aktiv && k.kontoart === 'standard'
  )

  const bankKonten = aktiveKonten.filter((k: Konto) => k.kontonummer.startsWith('18'))

  const kannBuchen =
    !!objektId &&
    !!aktivesWj &&
    aktivesWj.status !== 'abgeschlossen' &&
    !!form.buchungsdatum &&
    !!form.soll_konto &&
    !!form.haben_konto &&
    !!form.betrag &&
    Number(form.betrag) > 0

  const isPending = buchenMut.isPending || aktualisierenMut.isPending

  if (!objektId) {
    return <div className="p-6 text-gray-500">Bitte zuerst ein Objekt auswählen.</div>
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Dialogbuchhaltung</h1>

        {/* ── Wirtschaftsjahr-Selektor ── */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 font-medium">Wirtschaftsjahr:</span>
          {wirtschaftsjahre && wirtschaftsjahre.length > 0 ? (
            <select
              value={aktivesWj?.id ?? ''}
              onChange={e => setSelectedWjId(e.target.value || null)}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {wirtschaftsjahre.map(wj => (
                <option key={wj.id} value={wj.id}>
                  {wj.jahr}
                  {wj.status === 'abgeschlossen' ? ' (abgeschlossen)' : ''}
                </option>
              ))}
            </select>
          ) : (
            <span className="text-sm text-red-600">
              Kein Wirtschaftsjahr vorhanden —{' '}
              <a href="/objekte" className="underline">in Objektliste eröffnen</a>
            </span>
          )}
        </div>
      </div>

      {aktivesWj?.status === 'abgeschlossen' && (
        <div className="mb-4 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg text-sm text-amber-800">
          WJ {aktivesWj.jahr} ist abgeschlossen. Buchungen sind in diesem Jahr nicht mehr möglich.
        </div>
      )}

      {/* ── Stapel-Anzeige ── */}
      <div className="mb-4">
        {ausbuchenMut.isSuccess && (
          <div className="px-4 py-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 mb-2">
            Stapel ausgebucht — alle Buchungen sind festgeschrieben.
          </div>
        )}
        {aktuellerStapel ? (
          <div className="flex items-center gap-3 px-4 py-3 bg-blue-50 border border-blue-200 rounded-lg text-sm">
            <span className="text-blue-600 font-semibold">Aktueller Stapel:</span>
            <span className="text-blue-800">
              {aktuellerStapel.anzahl_buchungen} {aktuellerStapel.anzahl_buchungen === 1 ? 'Buchung' : 'Buchungen'}
              {' · '}
              {EUR(aktuellerStapel.gesamt_summe)}
            </span>
            <div className="ml-auto flex gap-2 items-center">
              <Button
                size="sm"
                onClick={() => ausbuchenMut.mutate(aktuellerStapel.id)}
                disabled={aktuellerStapel.anzahl_buchungen === 0 || ausbuchenMut.isPending}
              >
                {ausbuchenMut.isPending ? 'Ausbuche…' : 'Ausbuchen'}
              </Button>
              <button
                onClick={() => stapelAnlegenMut.mutate()}
                className="text-xs text-blue-500 hover:text-blue-700 underline"
              >
                Neuer Stapel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-500">
            Kein offener Stapel — wird beim ersten Buchen automatisch angelegt.
          </div>
        )}
      </div>

      {/* ── Modus-Tabs ── */}
      <div className="flex gap-1 mb-4 bg-gray-100 rounded-lg p-1 w-fit">
        {([
          { key: 'sachkonto',     label: 'Sachkontenbuchung' },
          { key: 'personenkonto', label: 'Personenkontobuchung' },
          { key: 'kreditor',      label: 'Kreditorenbuchung' },
        ] as const).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => { setModus(key); setForm(EMPTY); setZeForm(ZE_EMPTY) }}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${modus === key ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Personenkonto-Maske ── */}
      {modus === 'personenkonto' && (
        <div className="bg-white rounded-xl border shadow-sm p-6 mb-6">
          <div className="grid grid-cols-2 gap-4 mb-5">
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                Personenkonto (Eigentümer) *
              </label>
              <select
                value={zeForm.personenkonto_id}
                onChange={setZe('personenkonto_id')}
                className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">— Eigentümer wählen —</option>
                {(personenkonten ?? []).map((pk: { id: string; eigentuemer_name: string; einheit_nr: string; saldo_offen: number }) => (
                  <option key={pk.id} value={pk.id}>
                    {pk.eigentuemer_name} — {pk.einheit_nr} (offen: {pk.saldo_offen.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                Bankkonto (Sachkonto 18xxx) *
              </label>
              <select
                value={zeForm.bank_sachkonto_id}
                onChange={setZe('bank_sachkonto_id')}
                className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">— Bankkonto wählen —</option>
                {bankKonten.map((k: Konto) => (
                  <option key={k.id} value={k.id}>
                    {k.kontonummer} — {k.kontoname}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-5">
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                Buchungsdatum *
              </label>
              <input
                type="date"
                value={zeForm.buchungsdatum}
                onChange={setZe('buchungsdatum')}
                className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                Betrag (EUR) *
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={zeForm.betrag}
                onChange={setZe('betrag')}
                placeholder="0,00"
                className="border rounded-lg px-3 py-2 text-sm w-full text-right tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="mb-5">
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
              Buchungstext
            </label>
            <input
              type="text"
              value={zeForm.buchungstext}
              onChange={setZe('buchungstext')}
              placeholder="z.B. Überweisung Hausgeld Januar"
              className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {zeForm.personenkonto_id && zeForm.bank_sachkonto_id && zeForm.betrag && (
            <div className="mb-4 px-4 py-3 bg-blue-50 rounded-lg text-sm text-blue-800 border border-blue-100">
              Soll{' '}
              <span className="font-mono font-semibold">
                {bankKonten.find((k: Konto) => k.id === zeForm.bank_sachkonto_id)?.kontonummer}
              </span>
              {' '}/ Haben{' '}
              <span className="font-mono font-semibold">41xxx</span>
              {' '}—{' '}
              <span className="font-semibold tabular-nums">{EUR(zeForm.betrag)}</span>
              <span className="text-blue-600 ml-2 text-xs">Splits werden automatisch nach offenen Sollstellungen ermittelt</span>
            </div>
          )}

          {zeMut.isError && (
            <div className="mb-4 text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2 border border-red-200">
              {(zeMut.error as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Fehler beim Buchen.'}
            </div>
          )}

          {zeSuccess && (
            <div className="mb-4 text-sm text-green-700 bg-green-50 rounded-lg px-4 py-2 border border-green-200">
              Zahlungseingang erfolgreich gebucht. Offene Posten wurden aktualisiert.
            </div>
          )}

          <div className="flex justify-between items-center">
            <button
              type="button"
              onClick={() => setZeForm(ZE_EMPTY)}
              className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              Felder leeren
            </button>
            <Button
              onClick={() => zeMut.mutate()}
              disabled={!kannZeBuchen || zeMut.isPending}
            >
              {zeMut.isPending ? 'Buche…' : 'Zahlungseingang buchen'}
            </Button>
          </div>
        </div>
      )}

      {/* ── Buchungsmaske (Sachkonto + Kreditor) ── */}
      {(modus === 'sachkonto' || modus === 'kreditor') && (
      <div className={`bg-white rounded-xl border shadow-sm p-6 mb-6 ${editingId ? 'border-amber-300 ring-1 ring-amber-200' : ''}`}>

        {editingId && (
          <div className="mb-4 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700 font-medium">
            Buchung wird bearbeitet — Änderungen werden als Entwurf gespeichert.
          </div>
        )}

        {/* Zeile 1: Buchungsart / Datum / Belegnummer */}
        <div className="grid grid-cols-3 gap-4 mb-5">
          <div className="col-span-1">
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
              Buchungsart
            </label>
            <select
              value={form.buchungsart}
              onChange={set('buchungsart')}
              className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— wählen —</option>
              {(buchungsarten ?? []).map((ba: Buchungsart) => (
                <option key={ba.id} value={ba.id}>
                  {ba.nr} {ba.kuerzel}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
              Buchungsdatum *
            </label>
            <input
              type="date"
              value={form.buchungsdatum}
              onChange={set('buchungsdatum')}
              className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
              Belegnummer
            </label>
            <input
              type="text"
              value={form.belegnr}
              onChange={set('belegnr')}
              placeholder="z.B. RE-2026-001"
              className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Zeile 2: Soll / Betrag / Haben — T-Konten-Layout */}
        <div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-end mb-5">
          <div className="bg-blue-50 rounded-lg p-4 border border-blue-100">
            <label className="block text-xs font-semibold text-blue-700 uppercase tracking-wide mb-2">
              Soll *
            </label>
            <select
              value={form.soll_konto}
              onChange={set('soll_konto')}
              className="border rounded-lg px-3 py-2 text-sm w-full bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— Konto wählen —</option>
              {aktiveKonten.map((k: Konto) => (
                <option key={k.id} value={k.id}>
                  {k.kontonummer} — {k.kontoname}
                </option>
              ))}
            </select>
            {form.soll_konto && (
              <div className="mt-2 text-xs text-blue-600 font-mono">
                {aktiveKonten.find((k: Konto) => k.id === form.soll_konto)?.kontonummer}
              </div>
            )}
          </div>

          <div className="flex flex-col items-center gap-1 pb-1">
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide">
              Betrag *
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={form.betrag}
              onChange={set('betrag')}
              placeholder="0,00"
              className="border rounded-lg px-3 py-2 text-sm w-32 text-right tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-xs text-gray-400">EUR</span>
          </div>

          <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
              Haben *
            </label>
            <select
              value={form.haben_konto}
              onChange={set('haben_konto')}
              className="border rounded-lg px-3 py-2 text-sm w-full bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— Konto wählen —</option>
              {aktiveKonten.map((k: Konto) => (
                <option key={k.id} value={k.id}>
                  {k.kontonummer} — {k.kontoname}
                </option>
              ))}
            </select>
            {form.haben_konto && (
              <div className="mt-2 text-xs text-gray-500 font-mono">
                {aktiveKonten.find((k: Konto) => k.id === form.haben_konto)?.kontonummer}
              </div>
            )}
          </div>
        </div>

        {/* Buchungstext */}
        <div className="mb-5">
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
            Buchungstext
          </label>
          <textarea
            value={form.buchungstext}
            onChange={set('buchungstext')}
            rows={2}
            placeholder="Beschreibung der Buchung…"
            className="border rounded-lg px-3 py-2 text-sm w-full resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Vorschau */}
        {form.soll_konto && form.haben_konto && form.betrag && (
          <div className="mb-4 px-4 py-3 bg-gray-50 rounded-lg text-sm text-gray-600 border">
            <span className="font-mono font-semibold text-blue-700">
              {aktiveKonten.find((k: Konto) => k.id === form.soll_konto)?.kontonummer}
            </span>
            {' '}an{' '}
            <span className="font-mono font-semibold text-gray-700">
              {aktiveKonten.find((k: Konto) => k.id === form.haben_konto)?.kontonummer}
            </span>
            {' — '}
            <span className="font-semibold tabular-nums">{EUR(form.betrag)}</span>
            {form.buchungstext && <span className="text-gray-400"> | {form.buchungstext}</span>}
          </div>
        )}

        {(buchenMut.isError || aktualisierenMut.isError) && (
          <div className="mb-4 text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2 border border-red-200">
            Fehler beim Speichern der Buchung.
          </div>
        )}

        {success && (
          <div className="mb-4 text-sm text-green-700 bg-green-50 rounded-lg px-4 py-2 border border-green-200">
            {editingId ? 'Buchung aktualisiert.' : 'Buchung erfolgreich gespeichert.'}
          </div>
        )}

        <div className="flex justify-between items-center">
          <button
            type="button"
            onClick={editingId ? handleEditAbbrechen : () => setForm(EMPTY)}
            className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            {editingId ? 'Abbrechen' : 'Felder leeren'}
          </button>
          <div className="flex gap-2">
            {editingId ? (
              <Button
                onClick={() => aktualisierenMut.mutate()}
                disabled={!kannBuchen || isPending}
              >
                {aktualisierenMut.isPending ? 'Speichere…' : 'Änderung speichern'}
              </Button>
            ) : (
              <Button
                onClick={() => buchenMut.mutate()}
                disabled={!kannBuchen || isPending}
              >
                {buchenMut.isPending ? 'Speichere…' : 'Buchen'}
              </Button>
            )}
          </div>
        </div>
      </div>
      )}

      {/* ── Letzte Buchungen ── */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b bg-gray-50">
          <span className="text-sm font-semibold text-gray-700">Letzte Buchungen</span>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-2.5 text-gray-500 font-medium w-28">Datum</th>
              <th className="text-left px-4 py-2.5 text-gray-500 font-medium w-16">BA</th>
              <th className="text-left px-4 py-2.5 text-gray-500 font-medium">Soll</th>
              <th className="text-left px-4 py-2.5 text-gray-500 font-medium">Haben</th>
              <th className="text-left px-4 py-2.5 text-gray-500 font-medium">Text</th>
              <th className="text-right px-4 py-2.5 text-gray-500 font-medium w-28">Betrag</th>
              <th className="text-left px-4 py-2.5 text-gray-500 font-medium w-24">Status</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody>
            {(letzteZehn ?? []).length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center py-8 text-gray-400">
                  Noch keine Buchungen vorhanden
                </td>
              </tr>
            ) : (letzteZehn ?? []).map(b => (
              <tr
                key={b.id}
                className={`border-t hover:bg-gray-50 ${editingId === b.id ? 'bg-amber-50' : ''}`}
              >
                <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">{DATUM(b.buchungsdatum)}</td>
                <td className="px-4 py-2.5 text-gray-400 text-xs">{b.buchungsart_kuerzel || '—'}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-blue-700">{b.soll_konto_nr || '—'}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{b.haben_konto_nr || '—'}</td>
                <td className="px-4 py-2.5 text-gray-700 truncate max-w-[12rem]">{b.buchungstext || '—'}</td>
                <td className="px-4 py-2.5 text-right tabular-nums font-medium">{EUR(b.betrag)}</td>
                <td className="px-4 py-2.5">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    b.status === 'festgeschrieben'
                      ? 'bg-green-100 text-green-700'
                      : b.status === 'storniert'
                      ? 'bg-red-100 text-red-600'
                      : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    {b.status}
                  </span>
                </td>
                <td className="px-2 py-2.5 text-center">
                  {b.status === 'entwurf' && editingId !== b.id && (
                    <button
                      onClick={() => handleEditClick(b.id)}
                      title="Buchung bearbeiten"
                      className="text-gray-400 hover:text-blue-600 transition-colors"
                    >
                      ✏️
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
