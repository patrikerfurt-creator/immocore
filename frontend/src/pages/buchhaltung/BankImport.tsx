import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import { objekteApi } from '../../api/objekte'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/ui/Badge'

export function BankImport() {
  const [objektId, setObjektId] = useState('')
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: importe, isLoading } = useQuery({
    queryKey: ['bankimporte'],
    queryFn: buchhaltungApi.bankImporte,
  })

  const uploadMutation = useMutation({
    mutationFn: ({ objektId, file }: { objektId: string; file: File }) =>
      buchhaltungApi.uploadCamt(objektId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bankimporte'] })
      if (fileRef.current) fileRef.current.value = ''
      setError('')
    },
    onError: () => setError('Upload fehlgeschlagen.'),
  })

  function handleUpload() {
    const file = fileRef.current?.files?.[0]
    if (!file || !objektId) {
      setError('Bitte Objekt auswählen und Datei wählen.')
      return
    }
    uploadMutation.mutate({ objektId, file })
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Bankimport (camt.053)</h1>

      <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6">
        <h2 className="font-semibold text-gray-700 mb-4">Neue Datei importieren</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Objekt</label>
            <select
              className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={objektId}
              onChange={e => setObjektId(e.target.value)}
            >
              <option value="">Objekt wählen…</option>
              {objekte?.map(o => (
                <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">camt.053 Datei (XML)</label>
            <input ref={fileRef} type="file" accept=".xml" className="text-sm" />
          </div>
          <Button onClick={handleUpload} disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? 'Lädt…' : 'Importieren'}
          </Button>
        </div>
        {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
        {uploadMutation.isSuccess && (
          <p className="text-sm text-green-600 mt-2">Import erfolgreich.</p>
        )}
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Datei</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Importiert am</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Transaktionen</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {importe?.map(i => (
                <tr key={i.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-gray-600">{i.dateiname}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {new Date(i.importiert_am).toLocaleDateString('de-DE')}
                  </td>
                  <td className="px-4 py-3">{i.anzahl_transaktionen}</td>
                  <td className="px-4 py-3"><Badge value={i.status} /></td>
                  <td className="px-4 py-3">
                    <button
                      onClick={async () => {
                        const blob = await buchhaltungApi.sepaExport(i.id)
                        const url = URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        a.download = `sepa_${i.id}.xml`
                        a.click()
                        URL.revokeObjectURL(url)
                      }}
                      className="text-xs text-primary-600 hover:underline"
                    >
                      SEPA-Export
                    </button>
                  </td>
                </tr>
              ))}
              {importe?.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    Noch keine Imports vorhanden.
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
