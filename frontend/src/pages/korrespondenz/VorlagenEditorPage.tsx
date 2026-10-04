import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { vorlagenApi } from '../../api/korrespondenz'
import { VorlagenEditor } from './editor/VorlagenEditor'

/** Route-Seite des Editors: lädt Vorlage + Versionsliste (es gibt keinen Einzel-GET je Version). */
export function VorlagenEditorPage() {
  const { id, versionId } = useParams<{ id: string; versionId: string }>()

  const { data: vorlage, isLoading: vLaedt, error: vFehler } = useQuery({
    queryKey: ['korrespondenz-vorlage', id],
    queryFn: () => vorlagenApi.get(id!),
    enabled: !!id,
  })
  const { data: versionen, isLoading: verLaedt, error: verFehler } = useQuery({
    queryKey: ['korrespondenz-versionen', id],
    queryFn: () => vorlagenApi.versionen(id!),
    enabled: !!id,
  })

  if (vLaedt || verLaedt) return <p className="p-6 text-gray-400">Lade Vorlage…</p>
  if (vFehler || verFehler || !vorlage || !versionen) {
    return <p className="p-6 text-red-600">Vorlage konnte nicht geladen werden.</p>
  }
  const version = versionen.find(v => v.id === versionId)
  if (!version) return <p className="p-6 text-red-600">Version nicht gefunden.</p>

  return (
    <div className="p-6 space-y-3">
      <Link to={`/korrespondenz/vorlagen/${vorlage.id}`} className="text-sm text-primary-600 hover:underline">
        ← Versionen der Vorlage
      </Link>
      {/* key: bei Versionswechsel Editor-Zustand komplett neu aufbauen */}
      <VorlagenEditor key={version.id} vorlage={vorlage} version={version} />
    </div>
  )
}
