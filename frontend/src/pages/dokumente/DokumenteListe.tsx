import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { dokumenteApi } from '../../api/dokumente'
import { objekteApi } from '../../api/objekte'
import { Button } from '../../components/ui/Button'

const KATEGORIEN = ['allgemein', 'vertrag', 'rechnung', 'protokoll', 'beschluss', 'korrespondenz', 'sonstiges']

export function DokumenteListe() {
  const [searchParams] = useSearchParams()
  const [objektId, setObjektId] = useState(searchParams.get('objekt') ?? '')
  const [kategorie, setKategorie] = useState('')
  const [uploadObjektId, setUploadObjektId] = useState('')
  const [uploadKategorie, setUploadKategorie] = useState('allgemein')
  const [beschreibung, setBeschreibung] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: dokumente, isLoading } = useQuery({
    queryKey: ['dokumente', objektId, kategorie],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektId) params.objekt = objektId
      if (kategorie) params.kategorie = kategorie
      return dokumenteApi.list(params)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ file }: { file: File }) =>
      dokumenteApi.upload(uploadObjektId, file, uploadKategorie, beschreibung),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dokumente'] })
      if (fileRef.current) fileRef.current.value = ''
      setBeschreibung('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => dokumenteApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dokumente'] }),
  })

  function handleUpload() {
    const file = fileRef.current?.files?.[0]
    if (!file || !uploadObjektId) return
    uploadMutation.mutate({ file })
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Dokumente</h1>

      <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6">
        <h2 className="font-semibold text-gray-700 mb-3">Dokument hochladen</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Objekt</label>
            <select
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={uploadObjektId}
              onChange={e => setUploadObjektId(e.target.value)}
            >
              <option value="">Objekt wählen…</option>
              {objekte?.map(o => (
                <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Kategorie</label>
            <select
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={uploadKategorie}
              onChange={e => setUploadKategorie(e.target.value)}
            >
              {KATEGORIEN.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Beschreibung</label>
            <input
              type="text"
              value={beschreibung}
              onChange={e => setBeschreibung(e.target.value)}
              className="rounded border border-gray-300 px-3 py-2 text-sm w-48"
              placeholder="Optional…"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Datei</label>
            <input ref={fileRef} type="file" className="text-sm" />
          </div>
          <Button onClick={handleUpload} disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? 'Lädt…' : 'Hochladen'}
          </Button>
        </div>
      </div>

      <div className="flex gap-3 mb-4">
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={objektId}
          onChange={e => setObjektId(e.target.value)}
        >
          <option value="">Alle Objekte</option>
          {objekte?.map(o => (
            <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
          ))}
        </select>
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={kategorie}
          onChange={e => setKategorie(e.target.value)}
        >
          <option value="">Alle Kategorien</option>
          {KATEGORIEN.map(k => <option key={k} value={k}>{k}</option>)}
        </select>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Dateiname</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Kategorie</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Beschreibung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Hochgeladen am</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {dokumente?.map(d => (
                <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <a href={d.datei} target="_blank" rel="noopener noreferrer"
                       className="text-primary-600 hover:underline">
                      {d.dateiname}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{d.kategorie}</td>
                  <td className="px-4 py-3 text-gray-600">{d.beschreibung || '–'}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {new Date(d.hochgeladen_am).toLocaleDateString('de-DE')}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => deleteMutation.mutate(d.id)}
                      className="text-xs text-red-600 hover:underline"
                    >
                      Löschen
                    </button>
                  </td>
                </tr>
              ))}
              {dokumente?.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    Keine Dokumente gefunden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
