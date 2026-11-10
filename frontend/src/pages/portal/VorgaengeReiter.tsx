import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  meineVorgaenge,
  vorgangAnlegen,
  vorgangAntworten,
  vorgangDetail,
  vorgangTypen,
  NeuerVorgang,
  PortalVorgang,
  PortalVorgangDetail,
} from '../../api/portal'
import { apiFehler } from '../../api/fehler'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'

/**
 * Vorgänge-Reiter im Eigentümer-Portal (Spec 1, Kap. 8.2).
 *
 * Drei Ansichten in einer Komponente statt eigenem Routing: Liste, Detail
 * und Neu-Formular teilen sich Auswahlzustand und Einheit/WEG-Kontext, ein
 * eigener Reiter-Wechsel würde diesen Kontext nur unnötig verlieren.
 */
const STATUS_LABEL: Record<string, string> = {
  offen: 'Eingegangen',
  in_bearbeitung: 'In Bearbeitung',
  wartet_extern: 'Rückmeldung von Ihnen erforderlich',
  wiedervorlage: 'In Bearbeitung',
  erledigt: 'Abgeschlossen',
  storniert: 'Zurückgezogen',
}

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

function formatDatum(iso: string): string {
  const datum = new Date(iso)
  if (Number.isNaN(datum.getTime())) return iso
  return datum.toLocaleDateString('de-DE')
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className="inline-block shrink-0 px-2 py-0.5 rounded-full text-[11.5px] font-medium bg-portal-brand-soft text-portal-ink">
      {statusLabel(status)}
    </span>
  )
}

/** Meldung aus einer fehlgeschlagenen Mutation — 429 bekommt einen eigenen,
 * ruhigen Text statt der technischen Rate-Limit-Meldung des Servers. */
function anlegenFehlertext(fehler: unknown): string {
  const status = (fehler as { response?: { status?: number } })?.response?.status
  if (status === 429) {
    return 'Sie haben heute schon viele Vorgänge angelegt. Bitte melden Sie sich direkt bei der Verwaltung.'
  }
  return apiFehler(fehler, 'Der Vorgang konnte nicht angelegt werden.')
}

function VorgangListe({
  vorgaenge, onOeffnen, onNeu, neuVerfuegbar,
}: {
  vorgaenge: PortalVorgang[]
  onOeffnen: (id: string) => void
  onNeu: () => void
  neuVerfuegbar: boolean
}) {
  return (
    <div className="mt-4">
      {neuVerfuegbar && (
        <div className="flex justify-end mb-3">
          <Button variant="portal" size="sm" onClick={onNeu}>Neuer Vorgang</Button>
        </div>
      )}

      {vorgaenge.length === 0 ? (
        <p className="px-5 py-4 text-[13.5px] text-portal-soft bg-white border border-dashed border-portal-line rounded-[10px]">
          Für diese Einheit liegen derzeit keine Vorgänge vor.
        </p>
      ) : (
        <div className="bg-white border border-portal-line rounded-[10px] divide-y divide-portal-line overflow-hidden">
          {vorgaenge.map(v => (
            <button
              key={v.id}
              onClick={() => onOeffnen(v.id)}
              className="w-full text-left px-4 py-3 flex flex-col gap-1 hover:bg-portal-paper transition-colors"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-[13.5px] font-medium text-portal-ink">{v.betreff}</span>
                <StatusBadge status={v.status} />
              </div>
              <div className="flex items-center justify-between gap-3 text-[11.5px] text-portal-soft">
                <span>
                  {v.nummer}
                  {!v.einheit_id && v.objekt_bezeichnung ? ` · WEG-weit (${v.objekt_bezeichnung})` : ''}
                </span>
                <span>{formatDatum(v.erstellt_am)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Nachrichten der Verwaltung an den Eigentümer — im Portal linksbündig. Die
// eigenen Nachrichten des Eigentümers (portal_antwort + die ursprüngliche
// Beschreibung) stehen rechts.
const PORTAL_VON_VERWALTUNG = new Set([
  'antwort_freigegeben', 'antwort_vorschlag_freigegeben',
  'mail_antwort_gesendet', 'schreiben_versendet',
])

function PortalBubble({ eigen, text, label, datum }: {
  eigen: boolean; text: string; label: string; datum: string
}) {
  return (
    <div className={`flex ${eigen ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-[10px] border px-3.5 py-2.5 ${
        eigen ? 'bg-portal-brand-soft border-portal-brand-soft' : 'bg-white border-portal-line'
      }`}>
        <div className="flex items-center gap-2 flex-wrap text-[11px] text-portal-soft mb-1">
          <span className="font-medium text-portal-ink">{label}</span>
          <span>{datum}</span>
        </div>
        <p className="text-[13.5px] text-portal-ink whitespace-pre-wrap">{text}</p>
      </div>
    </div>
  )
}

function VorgangDetailAnsicht({ vorgang, onZurueck }: { vorgang: PortalVorgangDetail; onZurueck: () => void }) {
  const queryClient = useQueryClient()
  const [antwortText, setAntwortText] = useState('')
  const [fehler, setFehler] = useState('')

  const antwortMutation = useMutation({
    mutationFn: (text: string) => vorgangAntworten(vorgang.id, text),
    onSuccess: (aktualisiert) => {
      queryClient.setQueryData(['portal', 'vorgang', vorgang.id], aktualisiert)
      queryClient.invalidateQueries({ queryKey: ['portal', 'vorgaenge'] })
      setAntwortText('')
    },
    onError: (e) => setFehler(apiFehler(e, 'Ihre Antwort konnte nicht gesendet werden.')),
  })

  const nachrichten = [...vorgang.ereignisse].sort((a, b) => a.erstellt_am.localeCompare(b.erstellt_am))
  // Nach dem Abschluss ist keine weitere Rückantwort mehr sinnvoll.
  const antwortMoeglich = !['erledigt', 'storniert'].includes(vorgang.status)

  return (
    <div className="mt-4">
      <button onClick={onZurueck} className="text-[13px] font-medium text-portal-brand hover:underline mb-3">
        ← Zurück zur Liste
      </button>

      <div className="bg-white border border-portal-line rounded-[10px] px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-portal-ink">{vorgang.betreff}</h3>
            <p className="text-[11.5px] text-portal-soft mt-0.5">
              {vorgang.nummer} · erstellt am {formatDatum(vorgang.erstellt_am)}
              {!vorgang.einheit_id && vorgang.objekt_bezeichnung ? ` · WEG-weit (${vorgang.objekt_bezeichnung})` : ''}
            </p>
          </div>
          <StatusBadge status={vorgang.status} />
        </div>
      </div>

      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-portal-soft mt-6 mb-2">
        Verlauf
      </p>
      <div className="space-y-2.5">
        {/* Erste Nachricht: das ursprüngliche Anliegen des Eigentümers */}
        {vorgang.beschreibung && (
          <PortalBubble eigen label="Ihr Anliegen" datum={formatDatum(vorgang.erstellt_am)} text={vorgang.beschreibung} />
        )}
        {nachrichten.map((e, i) => {
          if (!e.text) return null
          const vonVerwaltung = PORTAL_VON_VERWALTUNG.has(e.typ)
          return (
            <PortalBubble
              key={i}
              eigen={!vonVerwaltung}
              label={vonVerwaltung ? 'Verwaltung' : 'Ihre Nachricht'}
              datum={formatDatum(e.erstellt_am)}
              text={e.text}
            />
          )
        })}
      </div>

      {/* Antwort-Composer */}
      {antwortMoeglich && (
        <div className="mt-4 bg-white border border-portal-line rounded-[10px] px-5 py-4">
          <label className="text-sm font-medium text-portal-ink">Antwort an die Verwaltung</label>
          <textarea
            value={antwortText}
            onChange={e => { setAntwortText(e.target.value); setFehler('') }}
            rows={3}
            placeholder="Ihre Nachricht…"
            className="mt-1 w-full rounded border px-3 py-2 text-sm outline-none transition border-portal-line focus:border-portal-brand focus:ring-1 focus:ring-portal-brand"
          />
          {fehler && <p className="text-sm text-portal-debit mt-1">{fehler}</p>}
          <div className="flex justify-end mt-2">
            <Button
              variant="portal"
              size="sm"
              disabled={antwortMutation.isPending || !antwortText.trim()}
              onClick={() => antwortMutation.mutate(antwortText)}
            >
              {antwortMutation.isPending ? 'Wird gesendet…' : 'Antwort senden'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function NeuerVorgangFormular({
  einheitId, onAbbrechen, onAngelegt,
}: {
  einheitId: string
  onAbbrechen: () => void
  onAngelegt: (id: string) => void
}) {
  const queryClient = useQueryClient()
  const typenQuery = useQuery({ queryKey: ['portal', 'vorgang-typen'], queryFn: vorgangTypen })
  const [typId, setTypId] = useState('')
  const [betreff, setBetreff] = useState('')
  const [beschreibung, setBeschreibung] = useState('')
  const [fehler, setFehler] = useState('')

  const mutation = useMutation({
    mutationFn: (werte: NeuerVorgang) => vorgangAnlegen(werte),
    onSuccess: (angelegt) => {
      queryClient.invalidateQueries({ queryKey: ['portal', 'vorgaenge'] })
      queryClient.setQueryData(['portal', 'vorgang', angelegt.id], angelegt)
      onAngelegt(angelegt.id)
    },
    onError: (e) => setFehler(anlegenFehlertext(e)),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFehler('')
    mutation.mutate({
      typ_id: typId,
      betreff,
      beschreibung: beschreibung || undefined,
      einheit_id: einheitId,
    })
  }

  return (
    <div className="mt-4 bg-white border border-portal-line rounded-[10px] px-5 py-4">
      <h3 className="text-base font-semibold text-portal-ink mb-3">Neuer Vorgang</h3>

      {typenQuery.isLoading && <p className="text-sm text-portal-soft">Wird geladen…</p>}
      {typenQuery.isError && (
        <p className="text-sm text-portal-debit">Die Vorgangstypen konnten nicht geladen werden.</p>
      )}

      {typenQuery.data && (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-portal-ink">Art des Anliegens</label>
            <select
              value={typId}
              onChange={e => setTypId(e.target.value)}
              required
              className="rounded border px-3 py-2 text-sm outline-none transition border-portal-line focus:border-portal-brand focus:ring-1 focus:ring-portal-brand"
            >
              <option value="" disabled>Bitte wählen…</option>
              {typenQuery.data.map(typ => (
                <option key={typ.id} value={typ.id}>{typ.bezeichnung}</option>
              ))}
            </select>
          </div>

          <Input
            label="Betreff"
            value={betreff}
            onChange={e => setBetreff(e.target.value)}
            required
          />

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-portal-ink">Beschreibung (optional)</label>
            <textarea
              value={beschreibung}
              onChange={e => setBeschreibung(e.target.value)}
              rows={4}
              className="rounded border px-3 py-2 text-sm outline-none transition border-portal-line focus:border-portal-brand focus:ring-1 focus:ring-portal-brand"
            />
          </div>

          {fehler && <p className="text-sm text-portal-debit">{fehler}</p>}

          <div className="flex gap-2">
            <Button type="submit" variant="portal" disabled={mutation.isPending || !typId || !betreff}>
              {mutation.isPending ? 'Wird gesendet…' : 'Vorgang anlegen'}
            </Button>
            <Button type="button" variant="portal-secondary" onClick={onAbbrechen} disabled={mutation.isPending}>
              Abbrechen
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}

export function VorgaengeReiter({ einheitId, objektId }: { einheitId: string; objektId: string }) {
  const [ansicht, setAnsicht] = useState<'liste' | 'neu'>('liste')
  const [geoeffneterId, setGeoeffneterId] = useState<string | null>(null)

  const listeQuery = useQuery({ queryKey: ['portal', 'vorgaenge'], queryFn: meineVorgaenge })
  const typenQuery = useQuery({ queryKey: ['portal', 'vorgang-typen'], queryFn: vorgangTypen })

  const detailQuery = useQuery({
    queryKey: ['portal', 'vorgang', geoeffneterId],
    queryFn: () => vorgangDetail(geoeffneterId as string),
    enabled: geoeffneterId !== null,
  })

  if (listeQuery.isLoading) {
    return <p className="mt-4 text-sm text-portal-soft">Wird geladen…</p>
  }
  if (listeQuery.isError) {
    return <p className="mt-4 text-sm text-portal-debit">Die Vorgänge konnten nicht geladen werden.</p>
  }

  if (geoeffneterId !== null) {
    if (detailQuery.isLoading) {
      return <p className="mt-4 text-sm text-portal-soft">Wird geladen…</p>
    }
    if (detailQuery.isError || !detailQuery.data) {
      return <p className="mt-4 text-sm text-portal-debit">Der Vorgang konnte nicht geladen werden.</p>
    }
    return (
      <VorgangDetailAnsicht vorgang={detailQuery.data} onZurueck={() => setGeoeffneterId(null)} />
    )
  }

  if (ansicht === 'neu') {
    return (
      <NeuerVorgangFormular
        einheitId={einheitId}
        onAbbrechen={() => setAnsicht('liste')}
        onAngelegt={(id) => {
          setAnsicht('liste')
          setGeoeffneterId(id)
        }}
      />
    )
  }

  // Zu dieser Einheit gehören ihre eigenen Vorgänge sowie WEG-weite Vorgänge
  // (ohne einheit_id) desselben Objekts — Zuordnung über objekt_id, nicht
  // über die Bezeichnung: zwei gleich benannte WEGs würden sonst vermischt.
  const vorgaenge = (listeQuery.data ?? []).filter(
    v => v.einheit_id === einheitId || (!v.einheit_id && v.objekt_id === objektId),
  )

  return (
    <VorgangListe
      vorgaenge={vorgaenge}
      onOeffnen={setGeoeffneterId}
      onNeu={() => setAnsicht('neu')}
      neuVerfuegbar={(typenQuery.data?.length ?? 0) > 0}
    />
  )
}
