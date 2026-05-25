import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { objekteApi } from '../api/objekte'
import { ticketsApi } from '../api/tickets'
import { rechnungenApi } from '../api/rechnungen'
import { prozesseApi } from '../api/prozesse'
import { useAuthStore } from '../stores/auth'
import client from '../api/client'

function StatCard({ label, value, to, color }: { label: string; value: number | string; to: string; color: string }) {
  return (
    <Link to={to} className={`rounded-lg p-5 text-white ${color} hover:opacity-90 transition-opacity`}>
      <p className="text-3xl font-bold">{value}</p>
      <p className="text-sm mt-1 opacity-90">{label}</p>
    </Link>
  )
}

function RechnungenCard({ objektbetreuer, frontoffice, freigaben, istFrontoffice }: {
  objektbetreuer: number; frontoffice: number; freigaben: number; istFrontoffice: boolean
}) {
  const total = objektbetreuer + freigaben + (istFrontoffice ? frontoffice : 0)
  const parts: string[] = []
  if (objektbetreuer > 0) parts.push(`${objektbetreuer} Prüffall Objekt`)
  if (istFrontoffice && frontoffice > 0) parts.push(`${frontoffice} Frontoffice-Queue`)
  if (freigaben > 0) parts.push(`${freigaben} Freigabe`)
  const tooltip = parts.length > 0 ? parts.join(', ') + '.' : 'Keine offenen Rechnungen.'

  return (
    <Link
      to="/rechnungen"
      title={tooltip}
      className="rounded-lg p-5 bg-orange-500 text-white hover:opacity-90 transition-opacity"
    >
      <p className="text-3xl font-bold">{total}</p>
      <p className="text-sm mt-1 opacity-90">Rechnungen in Prüfung</p>
      <div className="flex gap-2 mt-2 flex-wrap">
        {objektbetreuer > 0 && (
          <span className="text-xs bg-yellow-200 text-yellow-900 px-1.5 py-0.5 rounded font-medium">
            {objektbetreuer} Objektbetreuer
          </span>
        )}
        {istFrontoffice && frontoffice > 0 && (
          <span className="text-xs bg-orange-200 text-orange-900 px-1.5 py-0.5 rounded font-medium">
            {frontoffice} Frontoffice
          </span>
        )}
        {freigaben > 0 && (
          <span className="text-xs bg-blue-200 text-blue-900 px-1.5 py-0.5 rounded font-medium">
            {freigaben} Freigabe
          </span>
        )}
      </div>
    </Link>
  )
}

function ResetTestdatenButton() {
  const [bestaetige, setBestaetige] = useState(false)
  const [laeuft, setLaeuft] = useState(false)
  const [ergebnis, setErgebnis] = useState<string | null>(null)
  const qc = useQueryClient()

  async function ausfuehren() {
    setLaeuft(true)
    setErgebnis(null)
    try {
      const { data } = await client.post('/reset-testdaten/')
      const g = data.geloescht as Record<string, number>
      setErgebnis(`Gelöscht: ${g.buchungen} Buchungen, ${g.wkz_vorlagen} WKZ, ${g.wirtschaftsplaene} WP, ${g.rechnungen} Rechnungen`)
      qc.invalidateQueries()
    } catch {
      setErgebnis('Fehler beim Zurücksetzen.')
    } finally {
      setLaeuft(false)
      setBestaetige(false)
    }
  }

  return (
    <div className="mt-8 p-4 border border-red-200 rounded-lg bg-red-50">
      <p className="text-sm font-semibold text-red-700 mb-2">Testdaten zurücksetzen</p>
      <p className="text-xs text-red-600 mb-3">
        Löscht alle Buchungen, WKZ-Vorlagen, Wirtschaftspläne und Rechnungen unwiderruflich.
      </p>
      {!bestaetige ? (
        <button
          onClick={() => setBestaetige(true)}
          className="px-3 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700"
        >
          Zurücksetzen…
        </button>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={ausfuehren}
            disabled={laeuft}
            className="px-3 py-1.5 bg-red-700 text-white text-sm rounded hover:bg-red-800 disabled:opacity-50"
          >
            {laeuft ? 'Läuft…' : 'Ja, wirklich löschen'}
          </button>
          <button
            onClick={() => setBestaetige(false)}
            className="px-3 py-1.5 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300"
          >
            Abbrechen
          </button>
        </div>
      )}
      {ergebnis && <p className="text-xs text-red-700 mt-2">{ergebnis}</p>}
    </div>
  )
}

export function Dashboard() {
  const { username, istFrontoffice } = useAuthStore()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: tickets } = useQuery({ queryKey: ['tickets'], queryFn: () => ticketsApi.list() })
  const { data: rechnungen } = useQuery({
    queryKey: ['rechnungen-offen-widget'],
    queryFn: () => rechnungenApi.list({ zugewiesen_an: 'me' }),
  })
  const { data: meineObjektbetreuer } = useQuery({
    queryKey: ['rechnungen-objektbetreuer-me'],
    queryFn: () => rechnungenApi.list({ routing_ziel: 'objektbetreuer', zugewiesen_an: 'me' }),
  })
  const { data: meineFreigaben } = useQuery({
    queryKey: ['rechnungen-freigaben-me'],
    queryFn: () => rechnungenApi.list({ status: 'in_pruefung', zugewiesen_an: 'me' }),
  })
  const { data: frontofficeQueue } = useQuery({
    queryKey: ['frontoffice-inbox'],
    queryFn: () => rechnungenApi.list({ routing_ziel: 'frontoffice', zugewiesen_an: 'null' }),
    enabled: istFrontoffice,
  })
  const { data: prozesse } = useQuery({ queryKey: ['prozesse'], queryFn: () => prozesseApi.list({ status: 'aktiv' }) })

  const offeneTickets  = tickets?.filter(t => t.status === 'offen' || t.status === 'in_bearbeitung').length ?? 0
  const objektbetreuer = meineObjektbetreuer?.length ?? 0
  const freigaben      = meineFreigaben?.length ?? 0
  const frontoffice    = frontofficeQueue?.length ?? 0
  const aktiveProzesse = prozesse?.length ?? 0

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Übersicht</h1>
        <p className="text-gray-500 text-sm">Willkommen, {username}</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Verwaltete Objekte" value={objekte?.length ?? '–'} to="/objekte" color="bg-primary-600" />
        <StatCard label="Offene Tickets" value={offeneTickets} to="/tickets" color="bg-amber-500" />
        <RechnungenCard
          objektbetreuer={objektbetreuer}
          frontoffice={frontoffice}
          freigaben={freigaben}
          istFrontoffice={istFrontoffice}
        />
        <StatCard label="Aktive Prozesse" value={aktiveProzesse} to="/prozesse" color="bg-violet-600" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Letzte Tickets */}
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-semibold text-gray-800">Aktuelle Tickets</h2>
            <Link to="/tickets" className="text-xs text-primary-600 hover:underline">Alle anzeigen</Link>
          </div>
          {tickets?.slice(0, 5).map(t => (
            <div key={t.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
              <span className="text-sm text-gray-700 truncate">{t.titel}</span>
              <span className={`text-xs px-2 py-0.5 rounded ml-2 shrink-0 ${
                t.prioritaet === 'kritisch' ? 'bg-red-100 text-red-700' :
                t.prioritaet === 'hoch' ? 'bg-orange-100 text-orange-700' :
                'bg-gray-100 text-gray-600'
              }`}>{t.prioritaet}</span>
            </div>
          )) ?? <p className="text-sm text-gray-400">Keine Tickets</p>}
        </div>

        {/* Rechnungen */}
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-semibold text-gray-800">Rechnungen zur Prüfung</h2>
            <Link to="/rechnungen" className="text-xs text-primary-600 hover:underline">Alle anzeigen</Link>
          </div>
          {(() => {
            const relevant = rechnungen?.filter(r =>
              ['pruefung_match', 'nicht_erkannt', 'in_pruefung', 'erfasst'].includes(r.status)
            ) ?? []
            if (relevant.length === 0) return <p className="text-sm text-gray-400">Keine offenen Rechnungen</p>
            const GROUP_STYLE: Record<string, string> = {
              pruefung_match: 'bg-yellow-100 text-yellow-800',
              nicht_erkannt:  'bg-red-100 text-red-700',
              in_pruefung:    'bg-purple-100 text-purple-700',
              erfasst:        'bg-gray-100 text-gray-600',
            }
            const GROUP_LABEL: Record<string, string> = {
              pruefung_match: 'Prüffall',
              nicht_erkannt:  'nicht erkannt',
              in_pruefung:    'Freigabe',
              erfasst:        'erfasst',
            }
            return relevant.slice(0, 6).map(r => (
              <div key={r.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <div className="min-w-0">
                  <p className="text-sm text-gray-700 truncate">{r.kreditor_name || r.lieferant_name || '—'}</p>
                  <p className="text-xs text-gray-400">{r.rechnungsnummer || r.dateiname}</p>
                </div>
                <div className="flex items-center gap-2 ml-2 shrink-0">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${GROUP_STYLE[r.status] ?? 'bg-gray-100'}`}>
                    {GROUP_LABEL[r.status] ?? r.status}
                  </span>
                  <span className="text-sm font-medium text-gray-800">
                    {Number(r.betrag_brutto).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                  </span>
                </div>
              </div>
            ))
          })()}
        </div>
      </div>

      {(username === 'admin' || username === 'p.maurer' || username === 'p.maurer@demme-immobilien.de') && <ResetTestdatenButton />}
    </div>
  )
}
