import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { mailPosteingangApi, PosteingangMail } from '../../api/mailPosteingang'
import { objekteApi } from '../../api/objekte'
import { dokumenteApi } from '../../api/dokumente'
import { vorgaengeApi } from '../../api/vorgaenge'
import { Button } from '../../components/ui/Button'

/**
 * Posteingang für eingegangene Mails, die der Import nicht zuordnen konnte —
 * zweispaltig wie ein Mailprogramm: links die Liste, rechts die Mail.
 *
 * Die Mails liegen bereits vollständig im DMS; Aufbewahrung und Zuordnung
 * sind bewusst getrennt. Hier fehlt ihnen nur die Verortung. Deshalb ist
 * "Verwerfen" die einzige Aktion, die etwas löscht, und verlangt eine
 * Begründung.
 */

type Aktion = 'vorgang' | 'zuordnen' | 'ablegen' | 'verwerfen' | null

function datum(wert: string | null, kurz = false): string {
  if (!wert) return '—'
  return new Date(wert).toLocaleDateString('de-DE', kurz
    ? { day: '2-digit', month: '2-digit' }
    : { day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit' })
}

function fehlertext(fehler: unknown, ersatz: string): string {
  const antwort = (fehler as { response?: { data?: Record<string, unknown> } })?.response?.data
  if (!antwort) return ersatz
  if (typeof antwort.detail === 'string') return antwort.detail
  // DRF-Feldfehler: erste Meldung zeigen, statt [object Object].
  const erste = Object.values(antwort)[0]
  if (Array.isArray(erste) && typeof erste[0] === 'string') return erste[0]
  return ersatz
}

function istMailDatei(dateiname: string): boolean {
  return /\.(eml|msg)$/i.test(dateiname)
}

// ── Liste (links) ──────────────────────────────────────────────────────────

function ListenEintrag({ mail, aktiv, onWaehlen }: {
  mail: PosteingangMail
  aktiv: boolean
  onWaehlen: () => void
}) {
  const konfidenz = mail.ki_konfidenz ? Number(mail.ki_konfidenz) : null

  return (
    <li>
      <button
        type="button"
        onClick={onWaehlen}
        className={`w-full text-left px-3 py-2.5 border-l-2 transition-colors ${
          aktiv
            ? 'bg-blue-50 border-blue-600'
            : 'border-transparent hover:bg-gray-50'
        }`}
      >
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm font-medium text-gray-900 truncate">
            {mail.absender_name || mail.absender || '(kein Absender)'}
          </span>
          <span className="text-xs text-gray-400 whitespace-nowrap">
            {datum(mail.gesendet_am, true)}
          </span>
        </div>
        <p className="text-sm text-gray-700 truncate mt-0.5">
          {mail.betreff || '(ohne Betreff)'}
        </p>
        <div className="flex items-center gap-2 mt-1">
          {mail.ki_typ_code && (
            <span className="text-[11px] text-gray-500">
              {mail.ki_typ_code}
              {konfidenz !== null && ` · ${konfidenz.toFixed(2)}`}
            </span>
          )}
          {mail.anhaenge_anzahl > 0 && (
            <span className="text-[11px] text-gray-400">
              📎 {mail.anhaenge_anzahl}
            </span>
          )}
        </div>
      </button>
    </li>
  )
}

// ── Mailtext (rechts oben) ─────────────────────────────────────────────────

function MailVorschau({ mail }: { mail: PosteingangMail }) {
  const [html, setHtml] = useState<string | null>(null)
  const [fehlgeschlagen, setFehlgeschlagen] = useState(false)
  const mailDokument = mail.dokumente.find(d => istMailDatei(d.dateiname))

  useEffect(() => {
    if (!mailDokument) return
    let verworfen = false

    setHtml(null)
    setFehlgeschlagen(false)
    // kompakt: Betreff und Absender stehen bereits im Kopf darueber.
    dokumenteApi.mailVorschauHtml(mailDokument.id, true)
      .then(inhalt => { if (!verworfen) setHtml(inhalt) })
      .catch(() => { if (!verworfen) setFehlgeschlagen(true) })

    return () => { verworfen = true }
  }, [mailDokument?.id])

  if (!mailDokument || fehlgeschlagen) {
    // Rückfallebene: der beim Import gespeicherte Textauszug.
    return (
      <div className="p-4 text-sm text-gray-700 whitespace-pre-wrap">
        {fehlgeschlagen && (
          <p className="text-xs text-orange-700 mb-2">
            Die Originaldatei liess sich nicht lesen — gezeigt wird der beim
            Import gespeicherte Textauszug.
          </p>
        )}
        {mail.body_auszug || '(kein Text)'}
      </div>
    )
  }

  if (html === null) {
    return <p className="p-4 text-sm text-gray-400">Mail wird geladen…</p>
  }

  // sandbox="" verbietet alles: Skripte, Formulare, Navigation, und das
  // Dokument bekommt einen opaken Origin. Der Inhalt stammt von aussen —
  // das Backend escaped ihn bereits, dies ist die zweite Schranke.
  //
  // srcDoc statt src: eine blob:-URL koennte dieses iframe wegen des
  // opaken Origins gar nicht laden, es bliebe leer.
  return (
    <iframe
      srcDoc={html}
      sandbox=""
      title={mail.betreff || 'E-Mail'}
      className="w-full h-full border-0 bg-white"
    />
  )
}

// ── Aktionsbereich (rechts unten) ──────────────────────────────────────────

function Aktionsbereich({ mail, onFertig }: {
  mail: PosteingangMail
  onFertig: () => void
}) {
  const [aktion, setAktion] = useState<Aktion>(null)
  const [fehler, setFehler] = useState('')
  const [typId, setTypId] = useState('')
  const [objektId, setObjektId] = useState(mail.objekt ?? '')
  const [einheitId, setEinheitId] = useState(mail.einheit ?? '')
  const [betreff, setBetreff] = useState(mail.ki_betreff || mail.betreff)
  const [vorgangId, setVorgangId] = useState('')
  const [notiz, setNotiz] = useState('')

  // Beim Wechsel der Mail alles zurücksetzen — sonst stünde im Formular
  // noch die Auswahl der vorigen Mail.
  useEffect(() => {
    setAktion(null)
    setFehler('')
    setTypId('')
    setObjektId(mail.objekt ?? '')
    setEinheitId(mail.einheit ?? '')
    setBetreff(mail.ki_betreff || mail.betreff)
    setVorgangId('')
    setNotiz('')
  }, [mail.id])

  const { data: typen = [] } = useQuery({
    queryKey: ['vorgang-typen'],
    queryFn: () => vorgaengeApi.typenListe(),
    enabled: aktion === 'vorgang',
  })
  const { data: objekte = [] } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
    enabled: aktion === 'vorgang' || aktion === 'ablegen',
  })
  const { data: einheiten = [] } = useQuery({
    queryKey: ['einheiten', objektId],
    queryFn: () => objekteApi.listEinheiten({ objekt: objektId }),
    enabled: Boolean(objektId) && (aktion === 'vorgang' || aktion === 'ablegen'),
  })
  const { data: offeneVorgaenge = [] } = useQuery({
    queryKey: ['vorgaenge-offen', objektId],
    queryFn: () => vorgaengeApi.list(objektId ? { objekt: objektId } : undefined),
    enabled: aktion === 'zuordnen',
  })

  const mutation = useMutation({
    mutationFn: async () => {
      if (aktion === 'vorgang') {
        return mailPosteingangApi.vorgangAnlegen(mail.id, {
          typ: typId,
          objekt: einheitId ? null : objektId || null,
          einheit: einheitId || null,
          betreff,
          notiz,
        })
      }
      if (aktion === 'zuordnen') {
        return mailPosteingangApi.vorgangZuordnen(mail.id, vorgangId, notiz)
      }
      if (aktion === 'ablegen') {
        return mailPosteingangApi.nurAblegen(mail.id, {
          objekt: einheitId ? null : objektId || null,
          einheit: einheitId || null,
          notiz,
        })
      }
      return mailPosteingangApi.verwerfen(mail.id, notiz)
    },
    onSuccess: onFertig,
    onError: (f) => setFehler(fehlertext(f, 'Die Aktion ist fehlgeschlagen.')),
  })

  const kontextGewaehlt = Boolean(objektId || einheitId)
  const absendbar =
    (aktion === 'vorgang' && Boolean(typId) && kontextGewaehlt)
    || (aktion === 'zuordnen' && Boolean(vorgangId))
    || (aktion === 'ablegen' && kontextGewaehlt)
    || (aktion === 'verwerfen' && notiz.trim().length > 0)

  if (aktion === null) {
    return (
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => setAktion('vorgang')}>Vorgang anlegen</Button>
        <Button variant="secondary" onClick={() => setAktion('zuordnen')}>
          Zu Vorgang zuordnen
        </Button>
        <Button variant="secondary" onClick={() => setAktion('ablegen')}>
          Nur ablegen
        </Button>
        <Button variant="secondary" onClick={() => setAktion('verwerfen')}>
          Verwerfen
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {aktion === 'vorgang' && (
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-gray-700">
            Vorgangstyp
            <select className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
                    value={typId} onChange={e => setTypId(e.target.value)}>
              <option value="">— bitte wählen —</option>
              {typen.map(t => <option key={t.id} value={t.id}>{t.bezeichnung}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-700">
            Betreff
            <input className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
                   value={betreff} onChange={e => setBetreff(e.target.value)} />
          </label>
        </div>
      )}

      {(aktion === 'vorgang' || aktion === 'ablegen') && (
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-gray-700">
            Objekt
            <select className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
                    value={objektId}
                    onChange={e => { setObjektId(e.target.value); setEinheitId('') }}>
              <option value="">— bitte wählen —</option>
              {objekte.map(o => <option key={o.id} value={o.id}>{o.bezeichnung}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-700">
            Einheit (optional)
            <select className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
                    value={einheitId} onChange={e => setEinheitId(e.target.value)}
                    disabled={!objektId}>
              <option value="">— ganzes Objekt —</option>
              {einheiten.map(e => (
                <option key={e.id} value={e.id}>{e.einheit_nr} · {e.lage}</option>
              ))}
            </select>
          </label>
        </div>
      )}

      {aktion === 'zuordnen' && (
        <label className="text-xs text-gray-700">
          Bestehender Vorgang
          <select className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
                  value={vorgangId} onChange={e => setVorgangId(e.target.value)}>
            <option value="">— bitte wählen —</option>
            {offeneVorgaenge.map(v => (
              <option key={v.id} value={v.id}>{v.nummer} · {v.betreff}</option>
            ))}
          </select>
        </label>
      )}

      <label className="text-xs text-gray-700">
        {aktion === 'verwerfen' ? 'Begründung (Pflicht)' : 'Notiz (optional)'}
        <input className="mt-0.5 w-full border rounded px-2 py-1 text-sm"
               value={notiz} onChange={e => setNotiz(e.target.value)}
               placeholder={aktion === 'verwerfen' ? 'z. B. Werbung' : ''} />
      </label>

      {aktion === 'verwerfen' && (
        <p className="text-xs text-red-700">
          Die im DMS abgelegte Mail und ihre Anhänge werden gelöscht. Der
          Protokolleintrag bleibt, damit nachvollziehbar ist, dass die Mail
          einging und wer sie verworfen hat.
        </p>
      )}

      {fehler && <p className="text-xs text-red-700">{fehler}</p>}

      <div className="flex gap-2">
        <Button onClick={() => mutation.mutate()}
                disabled={!absendbar || mutation.isPending}>
          {mutation.isPending ? 'Wird gespeichert…' : 'Bestätigen'}
        </Button>
        <Button variant="secondary" onClick={() => { setAktion(null); setFehler('') }}>
          Abbrechen
        </Button>
      </div>
    </div>
  )
}

// ── Lesebereich (rechts) ───────────────────────────────────────────────────

function MailAnsicht({ mail, onFertig }: {
  mail: PosteingangMail
  onFertig: () => void
}) {
  const konfidenz = mail.ki_konfidenz ? Number(mail.ki_konfidenz) : null
  const unsicher = konfidenz !== null && konfidenz < 0.7
  const anhaenge = mail.dokumente.filter(d => !istMailDatei(d.dateiname))
  const mailDatei = mail.dokumente.find(d => istMailDatei(d.dateiname))

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Kopf */}
      <div className="px-5 py-3 border-b border-gray-200">
        <h2 className="text-base font-medium text-gray-900">
          {mail.betreff || '(ohne Betreff)'}
        </h2>
        <p className="text-xs text-gray-500 mt-1">
          {mail.absender_name ? `${mail.absender_name} <${mail.absender}>` : mail.absender}
          {' · '}{datum(mail.gesendet_am)}
        </p>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          {mail.ki_typ_code && (
            <span className={`text-xs px-1.5 py-0.5 rounded ${
              unsicher ? 'bg-yellow-100 text-yellow-800' : 'bg-blue-100 text-blue-800'
            }`}>
              KI: {mail.ki_typ_code}{konfidenz !== null && ` (${konfidenz.toFixed(2)})`}
            </span>
          )}
          {mail.ki_betreff && (
            <span className="text-xs text-gray-600">„{mail.ki_betreff}"</span>
          )}
          {mailDatei && (
            <button type="button"
                    onClick={() => dokumenteApi.openDatei(mailDatei.id)}
                    className="text-xs text-gray-500 hover:text-gray-800 hover:underline">
              Originaldatei
            </button>
          )}
        </div>
        {mail.personen_treffer > 1 && (
          <p className="text-xs text-orange-700 mt-1.5">
            Absenderadresse gehört zu {mail.personen_treffer} Personensätzen —
            möglicherweise eine Dublette in den Stammdaten.
          </p>
        )}
      </div>

      {/* Mailtext */}
      <div className="flex-1 min-h-0 overflow-auto bg-white">
        <MailVorschau mail={mail} />
      </div>

      {/* Anhänge */}
      {anhaenge.length > 0 && (
        <div className="px-5 py-2 border-t border-gray-200 flex flex-wrap items-center gap-3">
          <span className="text-xs text-gray-500">Anhänge:</span>
          {anhaenge.map(d => (
            <button key={d.id} type="button"
                    onClick={() => dokumenteApi.openDatei(d.id)}
                    className="text-xs text-blue-700 hover:underline max-w-xs truncate">
              📎 {d.dateiname}
            </button>
          ))}
        </div>
      )}

      {/* Aktionen */}
      <div className="px-5 py-3 border-t border-gray-200 bg-gray-50">
        <Aktionsbereich mail={mail} onFertig={onFertig} />
      </div>
    </div>
  )
}

// ── Seite ──────────────────────────────────────────────────────────────────

export default function MailPosteingang() {
  const qc = useQueryClient()
  const [gewaehlteId, setGewaehlteId] = useState<string | null>(null)

  const { data: mails = [], isLoading, isError } = useQuery({
    queryKey: ['mail-posteingang'],
    queryFn: () => mailPosteingangApi.list(),
  })

  // Nach dem Laden und nach jeder Entscheidung die erste offene Mail zeigen —
  // so arbeitet man den Stapel ohne Zusatzklick durch.
  useEffect(() => {
    if (mails.length === 0) { setGewaehlteId(null); return }
    if (!gewaehlteId || !mails.some(m => m.id === gewaehlteId)) {
      setGewaehlteId(mails[0].id)
    }
  }, [mails, gewaehlteId])

  const gewaehlt = mails.find(m => m.id === gewaehlteId) ?? null

  const nachEntscheidung = () => {
    qc.invalidateQueries({ queryKey: ['mail-posteingang'] })
    qc.invalidateQueries({ queryKey: ['vorgaenge'] })
    setGewaehlteId(null)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] min-h-[32rem]">
      <div className="flex items-baseline justify-between mb-3">
        <h1 className="text-xl font-semibold text-gray-900">Mail-Posteingang</h1>
        <span className="text-sm text-gray-500">
          {isLoading ? 'wird geladen…' : `${mails.length} offen`}
        </span>
      </div>

      {isError && (
        <p className="text-sm text-red-700">Die Liste konnte nicht geladen werden.</p>
      )}

      {!isLoading && !isError && mails.length === 0 && (
        <div className="flex-1 flex items-center justify-center border border-gray-200 rounded-lg bg-white">
          <p className="text-sm text-gray-500">
            Keine offenen Mails — alles zugeordnet.
          </p>
        </div>
      )}

      {mails.length > 0 && (
        <div className="flex-1 min-h-0 flex border border-gray-200 rounded-lg overflow-hidden bg-white">
          {/* Liste */}
          <div className="w-80 shrink-0 border-r border-gray-200 overflow-auto">
            <ul className="divide-y divide-gray-100">
              {mails.map(mail => (
                <ListenEintrag
                  key={mail.id}
                  mail={mail}
                  aktiv={mail.id === gewaehlteId}
                  onWaehlen={() => setGewaehlteId(mail.id)}
                />
              ))}
            </ul>
          </div>

          {/* Lesebereich */}
          <div className="flex-1 min-w-0">
            {gewaehlt
              ? <MailAnsicht mail={gewaehlt} onFertig={nachEntscheidung} />
              : <p className="p-5 text-sm text-gray-500">Mail links auswählen.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
