import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { buchhaltungApi } from '../../api/buchhaltung'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { useObjektStore } from '../../stores/objekt'
import type { BankBuchung, Konto, HausgeldSollstellung, KreditorOP } from '../../types'

const EUR   = (v: string | number) => Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
const DATUM = (s: string) => new Date(s).toLocaleDateString('de-DE')

const STATUS_LABELS: Record<string, string> = {
  erkannt:   'Erkannt',
  vorschlag: 'Vorschlag',
  unklar:    'Unklar',
  verbucht:  'Verbucht',
  storniert: 'Storniert',
  importiert: 'Importiert',
  manuell:   'Manuell',
  gebucht:   'Gebucht',
  ignoriert:  'Ignoriert',
  unbekannt: 'Unbekannt',
}

const QUELLE_LABELS: Record<string, string> = {
  e2e_id:          'End-to-End-ID',
  iban_ev:         'IBAN/Eigentümer',
  bank_match_regel:'Lernregel',
  iban_kreditor:   'Kreditor-IBAN',
  ki:              'KI-Vorschlag',
  keine:           'Keine',
}

type BuchungsTyp = 'sachkonto' | 'debitor' | 'kreditor'

const BUCHUNGSTYP_LABELS: Record<BuchungsTyp, string> = {
  sachkonto: 'Sachkontobuchung',
  debitor:   'Debitorisch',
  kreditor:  'Kreditorisch',
}

// ---------------------------------------------------------------------------
// Detail Slide-Over (Rechts-Panel)
// ---------------------------------------------------------------------------

function DetailSlideOver({
  buchung,
  objektId,
  onClose,
  onSaved,
}: {
  buchung: BankBuchung
  objektId: string
  onClose: () => void
  onSaved: (updated: BankBuchung) => void
}) {
  const istZugang      = Number(buchung.betrag) > 0
  const kannBearbeiten = !['verbucht', 'storniert'].includes(buchung.status)
  const kannStornieren = buchung.status === 'verbucht'

  const [buchungsTyp,   setBuchungsTyp]   = useState<BuchungsTyp>(istZugang ? 'debitor' : 'sachkonto')
  const [gegenkontoId,  setGegenkontoId]  = useState(buchung.erkannt_gegenkonto ?? '')
  const [selectedPKId,  setSelectedPKId]  = useState('')
  const [kreditorOPId,  setKreditorOPId]  = useState('')
  const [notiz,         setNotiz]         = useState(buchung.notiz ?? '')
  const [optOutLernen,  setOptOutLernen]  = useState(false)
  const [stornoGrund,   setStornoGrund]   = useState('')
  const [showStorno,    setShowStorno]    = useState(false)
  const qc = useQueryClient()

  const { data: konten } = useQuery({
    queryKey: ['konten', objektId, 'direktes_buchen'],
    queryFn: () => buchhaltungApi.konten(objektId, { direktes_buchen: true }),
    enabled: !!objektId && kannBearbeiten,
  })

  const { data: hgSollstellungen } = useQuery({
    queryKey: ['hg-sollstellungen-ebanking', objektId],
    queryFn: () => buchhaltungApi.hausgeldSollstellungen({ objekt: objektId, status: 'offen' }),
    enabled: !!objektId && kannBearbeiten && buchungsTyp === 'debitor',
  })

  const { data: kreditorOPs } = useQuery({
    queryKey: ['kreditor-ops', objektId],
    queryFn: () => buchhaltungApi.eBankingKreditorOPs({ objekt: objektId }),
    enabled: !!objektId && kannBearbeiten && buchungsTyp === 'kreditor',
  })

  // Alle Konten die direkt bebuchbar sind (standard + unterkonto, kein Summierungskonto)
  const buchbareKonten = (konten ?? []).filter((k: Konto) => k.aktiv && k.direktes_buchen && k.kontoart !== 'summierung')
  const alleKonten     = (konten ?? []).filter((k: Konto) => k.aktiv && k.direktes_buchen)

  function invalidate() {
    qc.invalidateQueries({ queryKey: ['e-banking-buchungen'] })
  }

  const verbuchenMut = useMutation({
    mutationFn: () => {
      if (buchungsTyp === 'debitor') {
        return buchhaltungApi.eBankingVerbuchen(buchung.id, {
          buchungs_typ: 'debitor',
          personenkonto_id: selectedPKId || undefined,
          notiz: notiz || undefined,
        })
      }
      if (buchungsTyp === 'kreditor') {
        return buchhaltungApi.eBankingVerbuchen(buchung.id, {
          buchungs_typ: 'kreditor',
          gegenkonto_id:  gegenkontoId || undefined,
          kreditor_op_id: kreditorOPId || undefined,
          notiz:          notiz || undefined,
          opt_out_lernen: optOutLernen,
        })
      }
      return buchhaltungApi.eBankingVerbuchen(buchung.id, {
        buchungs_typ:   'sachkonto',
        gegenkonto_id:  gegenkontoId || undefined,
        notiz:          notiz || undefined,
        opt_out_lernen: optOutLernen,
      })
    },
    onSuccess: (updated) => { invalidate(); onSaved(updated) },
  })

  const speichernMut = useMutation({
    mutationFn: () =>
      buchhaltungApi.eBankingSpeichern(buchung.id, {
        gegenkonto_id: gegenkontoId || null,
        notiz,
      }),
    onSuccess: (updated) => { invalidate(); onSaved(updated) },
  })

  const erkennungNeuMut = useMutation({
    mutationFn: () => buchhaltungApi.eBankingErkennungNeu(buchung.id),
    onSuccess: (updated) => { invalidate(); onSaved(updated) },
  })

  const stornoMut = useMutation({
    mutationFn: () => buchhaltungApi.eBankingStorno(buchung.id, stornoGrund),
    onSuccess: (updated) => { invalidate(); onSaved(updated) },
  })

  const kannVerbuchen =
    buchungsTyp === 'debitor' ? !!selectedPKId : !!gegenkontoId

  const isPending = verbuchenMut.isPending || speichernMut.isPending || stornoMut.isPending || erkennungNeuMut.isPending

  function errorOf(m: { isError: boolean; error: unknown }): string | null {
    if (!m.isError) return null
    const err = m.error as { response?: { data?: { error?: string } } }
    return err?.response?.data?.error ?? 'Unbekannter Fehler'
  }

  const anzeigeFehler = errorOf(verbuchenMut) ?? errorOf(speichernMut) ?? errorOf(stornoMut)

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative flex flex-col w-full max-w-lg h-full bg-white shadow-2xl overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-5 py-3 flex justify-between items-center z-10">
          <div className="flex items-center gap-3">
            <Badge value={buchung.status} label={STATUS_LABELS[buchung.status] ?? buchung.status} />
            <span className={`text-lg font-bold tabular-nums ${istZugang ? 'text-green-700' : 'text-red-700'}`}>
              {EUR(buchung.betrag)}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none px-2">✕</button>
        </div>

        <div className="flex-1 px-5 py-4 space-y-5">
          {/* Transaktionsdetails */}
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Transaktion</h3>
            <div className={`rounded-lg p-3 space-y-1.5 text-sm ${istZugang ? 'bg-green-50' : 'bg-red-50'}`}>
              {(
                [
                  ['Datum', DATUM(buchung.buchungsdatum)],
                  ['Kontrahent', buchung.auftraggeber_name || '—'],
                  buchung.auftraggeber_iban ? ['IBAN', buchung.auftraggeber_iban] : null,
                  buchung.verwendungszweck ? ['Verwendungszweck', buchung.verwendungszweck] : null,
                  buchung.end_to_end_id ? ['End-to-End-ID', buchung.end_to_end_id] : null,
                ] as (string[] | null)[]
              ).filter((x): x is string[] => x !== null).map(([label, val]) => (
                <div key={label} className="flex justify-between gap-4">
                  <span className="text-gray-500 flex-shrink-0">{label}</span>
                  <span className="text-right font-mono text-xs break-all">{val}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Erkennung */}
          {buchung.erkennungs_quelle && buchung.erkennungs_quelle !== 'keine' && (
            <section>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Erkennung</h3>
              <div className="bg-blue-50 rounded-lg p-3 space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Quelle</span>
                  <span>{QUELLE_LABELS[buchung.erkennungs_quelle] ?? buchung.erkennungs_quelle}</span>
                </div>
                {buchung.erkennungs_konfidenz != null && (
                  <div className="flex justify-between items-center gap-3">
                    <span className="text-gray-500 flex-shrink-0">Konfidenz</span>
                    <div className="flex items-center gap-2 flex-1 justify-end">
                      <div className="w-24 bg-gray-200 rounded-full h-1.5">
                        <div
                          className="bg-blue-500 h-1.5 rounded-full"
                          style={{ width: `${Math.round(Number(buchung.erkennungs_konfidenz) * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs tabular-nums">
                        {Math.round(Number(buchung.erkennungs_konfidenz) * 100)} %
                      </span>
                    </div>
                  </div>
                )}
                {buchung.erkennungs_begruendung && (
                  <div className="flex justify-between gap-4">
                    <span className="text-gray-500 flex-shrink-0">Begründung</span>
                    <span className="text-right text-xs">{buchung.erkennungs_begruendung}</span>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Erkanntes Gegenkonto (read-only) */}
          {buchung.erkannt_gegenkonto_detail && (
            <section>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Erkanntes Gegenkonto</h3>
              <div className="text-sm bg-gray-50 rounded-lg p-3">
                {buchung.erkannt_gegenkonto_detail.kontonummer} — {buchung.erkannt_gegenkonto_detail.kontoname}
              </div>
            </section>
          )}

          {/* Buchung */}
          {kannBearbeiten && (
            <section>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Buchung</h3>

              {/* Buchungstyp-Selektor */}
              <div className="flex gap-1 p-1 bg-gray-100 rounded-lg mb-4">
                {(Object.keys(BUCHUNGSTYP_LABELS) as BuchungsTyp[]).map(typ => (
                  <button
                    key={typ}
                    onClick={() => setBuchungsTyp(typ)}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors ${
                      buchungsTyp === typ
                        ? 'bg-white text-blue-700 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {BUCHUNGSTYP_LABELS[typ]}
                  </button>
                ))}
              </div>

              {/* Sachkonto: Gegenkonto-Auswahl */}
              {buchungsTyp === 'sachkonto' && (
                <div className="mb-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Gegenkonto <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={gegenkontoId}
                    onChange={e => setGegenkontoId(e.target.value)}
                    className="border rounded px-3 py-2 text-sm w-full"
                  >
                    <option value="">— Konto wählen —</option>
                    {buchbareKonten.map((k: Konto) => (
                      <option key={k.id} value={k.id}>
                        {k.kontonummer} — {k.kontoname}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Debitor: Hausgeld-Sollstellungen auswählen */}
              {buchungsTyp === 'debitor' && (
                <div className="mb-3">
                  <p className="text-xs text-gray-500 mb-2">Personenkonto auswählen</p>
                  <div className="border rounded overflow-hidden max-h-56 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-2 py-1.5 w-7" />
                          <th className="text-left px-2 py-1.5 text-gray-600">Eigentümer / PK</th>
                          <th className="text-left px-2 py-1.5 text-gray-600">Einheit</th>
                          <th className="text-left px-2 py-1.5 text-gray-600">Periode</th>
                          <th className="text-right px-2 py-1.5 text-gray-600">Offen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(hgSollstellungen as HausgeldSollstellung[] | undefined ?? []).length === 0 ? (
                          <tr>
                            <td colSpan={5} className="px-2 py-6 text-center text-gray-400">
                              Keine offenen Sollstellungen
                            </td>
                          </tr>
                        ) : (hgSollstellungen as HausgeldSollstellung[]).map((hg) => {
                          const isSelected = !!selectedPKId && selectedPKId === hg.personenkonto_id
                          const offen = Number(hg.soll_betrag) - Number(hg.ist_betrag)
                          const periode = hg.periode
                            ? new Date(hg.periode).toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' })
                            : '—'
                          return (
                            <tr
                              key={hg.id}
                              onClick={() => hg.personenkonto_id && setSelectedPKId(
                                selectedPKId === hg.personenkonto_id ? '' : hg.personenkonto_id
                              )}
                              className={`border-t cursor-pointer transition-colors ${isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                            >
                              <td className="px-2 py-2 text-center">
                                <input type="radio" checked={isSelected} readOnly className="pointer-events-none" />
                              </td>
                              <td className="px-2 py-2">
                                <span>{hg.ev_person_name || '—'}</span>
                                {hg.personenkonto_nr && (
                                  <span className="ml-1 text-gray-400">PK {hg.personenkonto_nr}</span>
                                )}
                              </td>
                              <td className="px-2 py-2 text-gray-500">{hg.ev_einheit_nr || '—'}</td>
                              <td className="px-2 py-2 text-gray-500">{periode}</td>
                              <td className="px-2 py-2 text-right tabular-nums">{EUR(offen)}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Kreditor: Gegenkonto + optionale Rechnungszuordnung */}
              {buchungsTyp === 'kreditor' && (
                <div className="mb-3 space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Gegenkonto <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={gegenkontoId}
                      onChange={e => setGegenkontoId(e.target.value)}
                      className="border rounded px-3 py-2 text-sm w-full"
                    >
                      <option value="">— Konto wählen —</option>
                      {alleKonten.map((k: Konto) => (
                        <option key={k.id} value={k.id}>
                          {k.kontonummer} — {k.kontoname}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Rechnung zuordnen <span className="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <div className="border rounded overflow-hidden max-h-48 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50 sticky top-0">
                          <tr>
                            <th className="px-2 py-1.5 w-7" />
                            <th className="text-left px-2 py-1.5 text-gray-600">Kreditor</th>
                            <th className="text-left px-2 py-1.5 text-gray-600">Re-Nr.</th>
                            <th className="text-right px-2 py-1.5 text-gray-600">Offen</th>
                            <th className="text-right px-2 py-1.5 text-gray-600">Fällig</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(kreditorOPs ?? []).length === 0 ? (
                            <tr>
                              <td colSpan={5} className="px-2 py-5 text-center text-gray-400">
                                Keine offenen Rechnungen
                              </td>
                            </tr>
                          ) : (kreditorOPs ?? []).map((op: KreditorOP) => (
                            <tr
                              key={op.id}
                              onClick={() => setKreditorOPId(kreditorOPId === op.id ? '' : op.id)}
                              className={`border-t cursor-pointer transition-colors ${
                                kreditorOPId === op.id ? 'bg-blue-50' : 'hover:bg-gray-50'
                              }`}
                            >
                              <td className="px-2 py-2 text-center">
                                <input type="radio" checked={kreditorOPId === op.id} readOnly className="pointer-events-none" />
                              </td>
                              <td className="px-2 py-2 max-w-[100px] truncate">{op.kreditor_name}</td>
                              <td className="px-2 py-2 font-mono text-gray-500">{op.rechnung_nr}</td>
                              <td className="px-2 py-2 text-right tabular-nums">{EUR(op.betrag_offen)}</td>
                              <td className="px-2 py-2 text-right text-gray-500">{DATUM(op.faellig_ab)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {/* Notiz */}
              <div className="mb-3">
                <label className="block text-sm font-medium text-gray-700 mb-1">Notiz (optional)</label>
                <input
                  type="text"
                  value={notiz}
                  onChange={e => setNotiz(e.target.value)}
                  className="border rounded px-3 py-2 text-sm w-full"
                  placeholder="Interne Notiz…"
                />
              </div>

              {buchungsTyp !== 'debitor' && (
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={optOutLernen}
                    onChange={e => setOptOutLernen(e.target.checked)}
                    className="rounded"
                  />
                  <span className="text-gray-700">Einzelfall — keine Regel speichern</span>
                </label>
              )}
            </section>
          )}

          {/* Verbucht-Info */}
          {buchung.status === 'verbucht' && (
            <section>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Verbuchung</h3>
              <div className="text-sm bg-green-50 rounded-lg p-3 space-y-1">
                {buchung.verbucht_am && <div>Am: {DATUM(buchung.verbucht_am)}</div>}
                {buchung.verbucht_von_username && <div>Von: {buchung.verbucht_von_username}</div>}
                {buchung.erkannt_gegenkonto_detail && (
                  <div>Konto: {buchung.erkannt_gegenkonto_detail.kontonummer} — {buchung.erkannt_gegenkonto_detail.kontoname}</div>
                )}
              </div>
            </section>
          )}

          {/* Storno-Dialog */}
          {kannStornieren && showStorno && (
            <section>
              <h3 className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-2">Storno</h3>
              <div className="space-y-2">
                <input
                  type="text"
                  value={stornoGrund}
                  onChange={e => setStornoGrund(e.target.value)}
                  className="border border-red-300 rounded px-3 py-2 text-sm w-full"
                  placeholder="Begründung für Storno (Pflicht)"
                />
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => { setShowStorno(false); setStornoGrund('') }}
                  >Abbrechen</Button>
                  <button
                    onClick={() => stornoMut.mutate()}
                    disabled={!stornoGrund || stornoMut.isPending}
                    className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                  >
                    {stornoMut.isPending ? 'Storniere…' : 'Storno bestätigen'}
                  </button>
                </div>
              </div>
            </section>
          )}

          {/* Fehler */}
          {anzeigeFehler && (
            <div className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{anzeigeFehler}</div>
          )}
        </div>

        {/* Footer-Buttons */}
        <div className="sticky bottom-0 bg-gray-50 border-t px-5 py-3 flex flex-col gap-2">
          {kannBearbeiten && (
            <>
              <Button
                onClick={() => verbuchenMut.mutate()}
                disabled={!kannVerbuchen || isPending}
                className="w-full justify-center"
              >
                {verbuchenMut.isPending ? 'Verbuche…' : 'Bestätigen & Verbuchen'}
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  onClick={() => speichernMut.mutate()}
                  disabled={isPending}
                  className="flex-1 justify-center"
                >
                  {speichernMut.isPending ? 'Speichere…' : 'Speichern'}
                </Button>
                <button
                  onClick={() => erkennungNeuMut.mutate()}
                  disabled={isPending}
                  className="px-3 py-1.5 text-xs text-gray-600 hover:text-gray-800 border rounded hover:bg-gray-100 disabled:opacity-50"
                  title="Erkennung erneut ausführen"
                >
                  ↺ Erkennung
                </button>
              </div>
            </>
          )}
          {kannStornieren && !showStorno && (
            <button
              onClick={() => setShowStorno(true)}
              className="text-sm text-red-600 hover:text-red-800 border border-red-200 rounded px-3 py-1.5 hover:bg-red-50"
            >
              Storno
            </button>
          )}
          <Button variant="secondary" onClick={onClose} className="w-full justify-center">Schließen</Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tabelle
// ---------------------------------------------------------------------------

function BuchungRow({
  bu,
  onClick,
}: {
  bu: BankBuchung
  onClick: () => void
}) {
  const istZugang = Number(bu.betrag) > 0
  return (
    <tr
      onClick={onClick}
      className="border-t hover:bg-blue-50 cursor-pointer transition-colors"
    >
      <td className="px-3 py-2.5">
        <Badge value={bu.status} label={STATUS_LABELS[bu.status] ?? bu.status} />
      </td>
      <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap text-sm">{DATUM(bu.buchungsdatum)}</td>
      <td className="px-3 py-2.5">
        <div className="text-sm">{bu.auftraggeber_name || '—'}</div>
        <div className="text-xs text-gray-400 font-mono">{bu.auftraggeber_iban}</div>
      </td>
      <td className="px-3 py-2.5 text-sm text-gray-600 max-w-[200px] truncate" title={bu.verwendungszweck}>
        {bu.verwendungszweck}
      </td>
      <td className={`px-3 py-2.5 text-right font-medium tabular-nums whitespace-nowrap text-sm ${istZugang ? 'text-green-700' : 'text-red-700'}`}>
        {EUR(bu.betrag)}
      </td>
      <td className="px-3 py-2.5 text-sm text-gray-600">
        {bu.erkannt_gegenkonto_detail
          ? `${bu.erkannt_gegenkonto_detail.kontonummer} ${bu.erkannt_gegenkonto_detail.kontoname}`
          : <span className="text-gray-300">—</span>}
      </td>
      <td className="px-3 py-2.5">
        {bu.erkennungs_konfidenz != null
          ? (
            <div className="flex items-center gap-1">
              <div className="w-16 bg-gray-200 rounded-full h-1.5">
                <div
                  className="bg-blue-400 h-1.5 rounded-full"
                  style={{ width: `${Math.round(Number(bu.erkennungs_konfidenz) * 100)}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 tabular-nums">
                {Math.round(Number(bu.erkennungs_konfidenz) * 100)} %
              </span>
            </div>
          )
          : <span className="text-gray-300 text-xs">—</span>}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

type TabKey = 'buchungen' | 'verbucht' | 'camt054'

export function EBanking() {
  const objektId = useObjektStore(s => s.selectedId)
  const [tab, setTab] = useState<TabKey>('buchungen')
  const [selected, setSelected] = useState<BankBuchung | null>(null)
  const [suche, setSuche] = useState('')
  const [datumVon, setDatumVon] = useState('')
  const [datumBis, setDatumBis] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  function buildParams(extra: Record<string, string> = {}) {
    const p: Record<string, string> = {}
    if (objektId) p.objekt = objektId
    if (suche)    p.suche = suche
    if (datumVon) p.datum_von = datumVon
    if (datumBis) p.datum_bis = datumBis
    return { ...p, ...extra }
  }

  const { data: buchungen, isLoading: loadingBuchungen } = useQuery({
    queryKey: ['e-banking-buchungen', 'aktiv', objektId, suche, datumVon, datumBis],
    queryFn: () => buchhaltungApi.eBankingBuchungen(buildParams({ status: 'erkannt,vorschlag,unklar,importiert' })),
    enabled: !!objektId && tab === 'buchungen',
  })

  const { data: verbucht, isLoading: loadingVerbucht } = useQuery({
    queryKey: ['e-banking-buchungen', 'verbucht', objektId, suche, datumVon, datumBis],
    queryFn: () => buchhaltungApi.eBankingBuchungen(buildParams({ status: 'verbucht,storniert' })),
    enabled: !!objektId && tab === 'verbucht',
  })

  const { data: camt054Liste } = useQuery({
    queryKey: ['camt054-liste'],
    queryFn: () => buchhaltungApi.eBankingCamt054Liste(),
    enabled: tab === 'camt054',
  })

  // Upload-Scan Trigger (camt-vorschau → camt-upload)
  const scanMut = useMutation({
    mutationFn: async (file: File) => {
      const vorschau = await buchhaltungApi.camtVorschauUpload(objektId!, file)
      if (vorschau.camt_typ === 'camt054') {
        return { importiert: 0, duplikate: 0, erkannt: 0, hinweis: vorschau.hinweis }
      }
      return buchhaltungApi.camtDirektImport(objektId!, {
        transaktionen: vorschau.transaktionen,
        import_datei: vorschau.import_datei,
      })
    },
    onSuccess: (result: { importiert?: number; duplikate?: number; erkannt?: number; hinweis?: string }) => {
      qc.invalidateQueries({ queryKey: ['e-banking-buchungen'] })
      if (fileInputRef.current) fileInputRef.current.value = ''
      if (result.hinweis) {
        alert(`Hinweis: ${result.hinweis}`)
      } else {
        alert(
          `Import abgeschlossen:\n${result.importiert ?? 0} importiert, ` +
          `${result.duplikate ?? 0} Duplikate, ${result.erkannt ?? 0} erkannt`
        )
      }
    },
  })

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) scanMut.mutate(file)
  }

  const rows = tab === 'buchungen' ? (buchungen ?? []) : (verbucht ?? [])
  const loading = tab === 'buchungen' ? loadingBuchungen : tab === 'verbucht' ? loadingVerbucht : false

  if (!objektId) {
    return (
      <div className="p-6 text-gray-500">Bitte zuerst ein Objekt in der Seitenleiste auswählen.</div>
    )
  }

  return (
    <div>
      {selected && (
        <DetailSlideOver
          buchung={selected}
          objektId={objektId}
          onClose={() => setSelected(null)}
          onSaved={(updated) => setSelected(updated)}
        />
      )}

      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold text-gray-900">E-Banking</h1>
        <div className="flex gap-2">
          <Link
            to="/buchhaltung/ebanking/regeln"
            className="text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded px-3 py-1.5"
          >
            Lernregeln
          </Link>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xml,.camt"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button
            variant="secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={scanMut.isPending}
          >
            {scanMut.isPending ? 'Importiere…' : 'CAMT importieren'}
          </Button>
        </div>
      </div>

      {scanMut.isError && (
        <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          Import-Fehler: {(scanMut.error as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Unbekannter Fehler'}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b mb-4">
        {([['buchungen', 'Buchungen'], ['verbucht', 'Verbucht'], ['camt054', 'camt.054']] as [TabKey, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === key
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Filter (Buchungen + Verbucht) */}
      {tab !== 'camt054' && (
        <div className="flex gap-3 mb-4 flex-wrap">
          <input
            type="text"
            placeholder="Kontrahent / Verwendungszweck…"
            value={suche}
            onChange={e => setSuche(e.target.value)}
            className="border rounded px-3 py-2 text-sm w-64"
          />
          <input
            type="date"
            value={datumVon}
            onChange={e => setDatumVon(e.target.value)}
            className="border rounded px-3 py-2 text-sm"
            title="Datum von"
          />
          <input
            type="date"
            value={datumBis}
            onChange={e => setDatumBis(e.target.value)}
            className="border rounded px-3 py-2 text-sm"
            title="Datum bis"
          />
          {(suche || datumVon || datumBis) && (
            <button
              onClick={() => { setSuche(''); setDatumVon(''); setDatumBis('') }}
              className="text-sm text-gray-400 hover:text-gray-600 px-2"
            >
              Filter zurücksetzen
            </button>
          )}
        </div>
      )}

      {/* Buchungen-Tabelle */}
      {tab !== 'camt054' && (
        loading ? (
          <div className="text-gray-400 text-sm">Lade…</div>
        ) : (
          <div className="bg-white rounded-lg border overflow-hidden">
            <table className="w-full text-sm table-fixed">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-3 py-3 text-gray-600 font-medium w-28">Status</th>
                  <th className="text-left px-3 py-3 text-gray-600 font-medium w-28">Datum</th>
                  <th className="text-left px-3 py-3 text-gray-600 font-medium w-52">Kontrahent</th>
                  <th className="text-left px-3 py-3 text-gray-600 font-medium">Verwendungszweck</th>
                  <th className="text-right px-3 py-3 text-gray-600 font-medium w-28">Betrag</th>
                  <th className="text-left px-3 py-3 text-gray-600 font-medium w-48">Gegenkonto</th>
                  <th className="text-left px-3 py-3 text-gray-600 font-medium w-32">Konfidenz</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-10 text-gray-400">Keine Einträge</td>
                  </tr>
                ) : rows.map((bu: BankBuchung) => (
                  <BuchungRow key={bu.id} bu={bu} onClick={() => setSelected(bu)} />
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* camt.054-Tab */}
      {tab === 'camt054' && (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-600">Zeitpunkt</th>
                <th className="text-left px-4 py-3 text-gray-600">Datei / Ordner</th>
                <th className="text-left px-4 py-3 text-gray-600">Status</th>
                <th className="text-left px-4 py-3 text-gray-600">Notiz</th>
              </tr>
            </thead>
            <tbody>
              {!camt054Liste || (camt054Liste as unknown[]).length === 0 ? (
                <tr>
                  <td colSpan={4} className="text-center py-10 text-gray-400">
                    Keine camt.054-Importe vorhanden
                  </td>
                </tr>
              ) : (camt054Liste as Record<string, string>[]).map((log) => (
                <tr key={log.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{DATUM(log.zeitpunkt)}</td>
                  <td className="px-4 py-3 text-gray-600 text-xs font-mono truncate max-w-xs">{log.import_ordner || '—'}</td>
                  <td className="px-4 py-3">
                    <Badge value={log.status ?? 'pending_mahnwesen_spec'} label="Geparkt" />
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{log.notiz}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
