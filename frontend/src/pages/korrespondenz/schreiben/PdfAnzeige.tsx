import { useEffect, useRef, useState } from 'react'
import { korrespondenzFehlerText } from '../../../api/korrespondenz'

interface Props {
  /** Titel des iframes (auch Zugänglichkeitsname). */
  titel: string
  /** Liefert das PDF als Blob (Standard-Accept, `responseType: 'blob'`). */
  laden: () => Promise<Blob>
  /** Ändert sich dieser Wert, wird das PDF neu geladen (z. B. nach einer Textanpassung). */
  neuLadenKey?: string | number
  /** Dateiname für den Download-Link. */
  dateiname?: string
  hoehe?: string
}

/** Lädt ein PDF als Blob und zeigt es in einem iframe (blob-URL) samt Download-Link. */
export function PdfAnzeige({ titel, laden, neuLadenKey, dateiname = 'schreiben.pdf', hoehe = 'h-[75vh]' }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const [laedt, setLaedt] = useState(true)
  const ladenRef = useRef(laden)
  ladenRef.current = laden

  useEffect(() => {
    let abgebrochen = false
    let neueUrl: string | null = null
    setLaedt(true)
    setFehler(null)
    ladenRef.current()
      .then(blob => {
        if (abgebrochen) return
        const pdf = blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' })
        neueUrl = URL.createObjectURL(pdf)
        setUrl(neueUrl)
        setLaedt(false)
      })
      .catch(async error => {
        const text = await korrespondenzFehlerText(error, 'PDF konnte nicht geladen werden.')
        if (abgebrochen) return
        setUrl(null)
        setFehler(text)
        setLaedt(false)
      })
    return () => {
      abgebrochen = true
      if (neueUrl) URL.revokeObjectURL(neueUrl)
    }
  }, [neuLadenKey])

  return (
    <div className="space-y-2">
      {laedt && <p className="text-sm text-gray-400">Lade PDF…</p>}
      {fehler && <p role="alert" className="text-sm text-red-600">{fehler}</p>}
      {url && (
        <>
          <a href={url} download={dateiname} className="text-sm text-primary-600 hover:underline">
            PDF herunterladen
          </a>
          <iframe title={titel} src={url} className={`w-full ${hoehe} border border-gray-300 rounded`} />
        </>
      )}
    </div>
  )
}
