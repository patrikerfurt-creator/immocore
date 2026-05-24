import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import { wirtschaftsjahreApi } from '../../api/wirtschaftsjahre'
import { objekteApi } from '../../api/objekte'
import type { Konto, Verteilerschluessel, Wirtschaftsjahr } from '../../types'

const kontoartLabel: Record<string, string> = {
  standard: 'Standard',
  summierung: 'Summierung',
  unterkonto: 'Unterkonto',
}

const kontoartStyle: Record<string, string> = {
  standard: 'bg-blue-50 text-blue-700',
  summierung: 'bg-purple-50 text-purple-700',
  unterkonto: 'bg-gray-100 text-gray-600',
}

type FormState = {
  kontonummer: string
  kontoname: string
  kontoart: 'standard' | 'summierung' | 'unterkonto'
  abrechnungsart: string
  verteilerschluessel: string
  direktes_buchen: boolean
  arge_konto: boolean
  arge_kostenart: string
  aktiv: boolean
}

function emptyForm(): FormState {
  return { kontonummer: '', kontoname: '', kontoart: 'standard', abrechnungsart: '', verteilerschluessel: '', direktes_buchen: true, arge_konto: false, arge_kostenart: '', aktiv: true }
}

function kontoToForm(k: Konto): FormState {
  return {
    kontonummer: k.kontonummer,
    kontoname: k.kontoname,
    kontoart: k.kontoart,
    abrechnungsart: k.abrechnungsart ?? '',
    verteilerschluessel: k.verteilerschluessel ?? '',
    direktes_buchen: k.direktes_buchen,
    arge_konto: k.arge_konto,
    arge_kostenart: k.arge_kostenart ?? '',
    aktiv: k.aktiv,
  }
}

function KontoModal({
  konto,
  objektId,
  wirtschaftsjahrId,
  onClose,
}: {
  konto: Konto | null
  objektId: string
  wirtschaftsjahrId: string | undefined
  onClose: () => void
}) {
  const qc = useQueryClient()
  const isEdit = konto !== null
  const [form, setForm] = useState<FormState>(konto ? kontoToForm(konto) : emptyForm())
  const [error, setError] = useState<string | null>(null)

  const { data: vsList = [] } = useQuery<Verteilerschluessel[]>({
    queryKey: ['verteilerschluessel', objektId],
    queryFn: () => objekteApi.verteilerschluessel({ objekt: objektId }),
  })

  const isSummierung = form.kontoart === 'summierung'
  const isUnterkonto = form.kontoart === 'unterkonto'

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(f => ({ ...f, [key]: value }))
  }

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        objekt: objektId,
        wirtschaftsjahr: wirtschaftsjahrId,
        kontonummer: form.kontonummer,
        kontoname: form.kontoname,
        kontoart: form.kontoart,
        abrechnungsart: form.abrechnungsart || null,
        verteilerschluessel: form.verteilerschluessel || null,
        direktes_buchen: isSummierung ? false : form.direktes_buchen,
        arge_konto: isUnterkonto ? true : form.arge_konto,
        arge_kostenart: form.arge_kostenart || null,
        aktiv: form.aktiv,
      }
      if (isEdit) return buchhaltungApi.updateKonto(konto!.id, payload)
      return buchhaltungApi.createKonto(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['konten', objektId] })
      onClose()
    },
    onError: (e: Error) => setError(e.message || 'Fehler beim Speichern'),
  })

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">{isEdit ? 'Konto bearbeiten' : 'Neues Konto'}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
        </div>

        <form
          onSubmit={e => { e.preventDefault(); setError(null); mutation.mutate() }}
          className="px-6 py-4 space-y-4"
        >
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Kontonummer *</label>
              <input
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary-500"
                value={form.kontonummer}
                onChange={e => set('kontonummer', e.target.value)}
                maxLength={6}
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Kontoart</label>
              <select
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                value={form.kontoart}
                onChange={e => set('kontoart', e.target.value as FormState['kontoart'])}
              >
                <option value="standard">Standard</option>
                <option value="summierung">Summierung</option>
                <option value="unterkonto">Unterkonto</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Kontoname *</label>
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={form.kontoname}
              onChange={e => set('kontoname', e.target.value)}
              maxLength={120}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Abrechnungsart</label>
              <input
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                value={form.abrechnungsart}
                onChange={e => set('abrechnungsart', e.target.value)}
                maxLength={3}
                placeholder="z.B. 900"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Verteilerschlüssel</label>
              <select
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                value={form.verteilerschluessel}
                onChange={e => set('verteilerschluessel', e.target.value)}
              >
                <option value="">— kein —</option>
                {vsList.map(vs => (
                  <option key={vs.id} value={vs.schluessel}>
                    {vs.schluessel} – {vs.bezeichnung}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">ARGE Kostenart</label>
              <input
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                value={form.arge_kostenart}
                onChange={e => set('arge_kostenart', e.target.value)}
                maxLength={20}
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={isSummierung ? false : form.direktes_buchen}
                disabled={isSummierung}
                onChange={e => set('direktes_buchen', e.target.checked)}
                className="rounded"
              />
              Direktes Buchen
              {isSummierung && <span className="text-xs text-gray-400">(Summierungskonto)</span>}
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={isUnterkonto ? true : form.arge_konto}
                disabled={isUnterkonto}
                onChange={e => set('arge_konto', e.target.checked)}
                className="rounded"
              />
              ARGE Konto
              {isUnterkonto && <span className="text-xs text-gray-400">(Unterkonto)</span>}
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={form.aktiv}
                onChange={e => set('aktiv', e.target.checked)}
                className="rounded"
              />
              Aktiv
            </label>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-3 pt-2 border-t border-gray-100">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-700 disabled:opacity-50"
            >
              {mutation.isPending ? 'Speichern…' : 'Speichern'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function KontenplanPage() {
  const [searchParams] = useSearchParams()
  const objektId = searchParams.get('objekt')
  const [modalKonto, setModalKonto] = useState<Konto | 'new' | null>(null)
  const [selectedWjId, setSelectedWjId] = useState<string | null>(null)

  const { data: wirtschaftsjahre = [], isLoading: wjLaden } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => wirtschaftsjahreApi.list({ objekt: objektId! }),
    enabled: !!objektId,
    select: (wjs: Wirtschaftsjahr[]) => [...wjs].sort((a, b) => b.jahr - a.jahr),
  })

  const aktivesWj: Wirtschaftsjahr | undefined = (() => {
    if (!wirtschaftsjahre.length) return undefined
    if (selectedWjId) return wirtschaftsjahre.find(w => w.id === selectedWjId)
    return wirtschaftsjahre.find(w => w.status === 'offen') ?? wirtschaftsjahre[0]
  })()

  // Konten laden sobald WJ-Query fertig ist (mit oder ohne WJ-Filter)
  const { data: konten = [], isLoading: kontenLaden } = useQuery({
    queryKey: ['konten', objektId, aktivesWj?.id ?? 'alle'],
    queryFn: () => buchhaltungApi.konten(objektId!, aktivesWj ? { wirtschaftsjahr: aktivesWj.id } : undefined),
    enabled: !!objektId && !wjLaden,
  })

  const isLoading = wjLaden || kontenLaden

  if (!objektId) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Kontenplan</h1>
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
          <p className="text-gray-500 mb-3">Bitte wählen Sie zuerst ein Objekt aus.</p>
          <Link to="/objekte" className="text-primary-600 hover:underline text-sm">→ Zur Objektliste</Link>
        </div>
      </div>
    )
  }

  if (isLoading) return <p className="text-gray-400">Laden…</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Kontenplan</h1>
        <div className="flex items-center gap-4">
          {/* Wirtschaftsjahr-Selektor (nur wenn WJs vorhanden) */}
          {wjLaden ? (
            <span className="text-sm text-gray-400">Lade WJ…</span>
          ) : wirtschaftsjahre.length > 0 ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 font-medium">Wirtschaftsjahr:</span>
              <select
                value={aktivesWj?.id ?? ''}
                onChange={e => setSelectedWjId(e.target.value || null)}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {wirtschaftsjahre.map(wj => (
                  <option key={wj.id} value={wj.id}>
                    {wj.jahr}{wj.status === 'abgeschlossen' ? ' (abgeschlossen)' : ''}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          <span className="text-sm text-gray-400">{konten.length} Konten</span>
          <button
            onClick={() => setModalKonto('new')}
            disabled={!aktivesWj}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded hover:bg-primary-700 disabled:opacity-40"
          >
            + Neues Konto
          </button>
        </div>
      </div>

      {aktivesWj?.status === 'abgeschlossen' && (
        <div className="mb-4 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg text-sm text-amber-800">
          WJ {aktivesWj.jahr} ist abgeschlossen. Änderungen am Kontenplan sind nicht mehr möglich.
        </div>
      )}

      {konten.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
          <p className="text-gray-500">
            {aktivesWj ? `Keine Konten für WJ ${aktivesWj.jahr} vorhanden.` : 'Keine Konten vorhanden.'}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Kto.-Nr.</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Kontoname</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Art</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Abrechnungsart</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Verteilerschlüssel</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Direktbuchen</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">ARGE</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Aktiv</th>
              </tr>
            </thead>
            <tbody>
              {konten.map((k) => (
                <tr
                  key={k.id}
                  onClick={() => setModalKonto(k)}
                  className={`border-b border-gray-50 hover:bg-primary-50 cursor-pointer transition-colors ${!k.aktiv ? 'opacity-50' : ''}`}
                >
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{k.kontonummer}</td>
                  <td className="px-4 py-2.5 text-gray-800">
                    {k.kontoart === 'unterkonto' && <span className="mr-1 text-gray-300">↪</span>}
                    {k.kontoname}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${kontoartStyle[k.kontoart] ?? 'bg-gray-50 text-gray-700'}`}>
                      {kontoartLabel[k.kontoart] ?? k.kontoart}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 text-xs font-mono">{k.abrechnungsart || '–'}</td>
                  <td className="px-4 py-2.5 text-gray-600 text-xs font-mono">{k.verteilerschluessel || '–'}</td>
                  <td className="px-4 py-2.5 text-center text-gray-600">{k.direktes_buchen ? '✓' : ''}</td>
                  <td className="px-4 py-2.5 text-center text-gray-600">{k.arge_konto ? '✓' : ''}</td>
                  <td className="px-4 py-2.5 text-center">
                    {k.aktiv
                      ? <span className="text-green-600 text-xs font-medium">Aktiv</span>
                      : <span className="text-gray-400 text-xs">Inaktiv</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalKonto && (
        <KontoModal
          konto={modalKonto === 'new' ? null : modalKonto}
          objektId={objektId}
          wirtschaftsjahrId={aktivesWj?.id}
          onClose={() => setModalKonto(null)}
        />
      )}
    </div>
  )
}
