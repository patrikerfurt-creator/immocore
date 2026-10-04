import { useState } from 'react'
import { schreibenApi } from '../../../api/korrespondenz'
import type { Serienlauf } from '../../../types'
import { PdfAnzeige } from '../schreiben/PdfAnzeige'

/**
 * Schritt 4 (Spec 7.4 Punkt 4): Kennzahlen, Vorschau mit den vom Backend gezogenen 3 zufälligen
 * Empfängern (PDF je Empfänger auf Abruf) und die Liste der nicht erzeugbaren Schreiben mit Ursache.
 */
export function SerienbriefVorschau({ lauf }: { lauf: Serienlauf }) {
  const [offen, setOffen] = useState<string | null>(null)
  const { zaehler, vorschau, nicht_erzeugbar: nichtErzeugbar } = lauf

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-3 gap-3 text-sm max-w-lg">
        <div className="bg-gray-50 rounded p-3">
          <dt className="text-gray-500">Schreiben gesamt</dt>
          <dd className="text-lg font-semibold">{zaehler.gesamt}</dd>
        </div>
        <div className="bg-green-50 rounded p-3">
          <dt className="text-gray-500">Erzeugbar</dt>
          <dd className="text-lg font-semibold text-green-800">{vorschau.erzeugbar_anzahl}</dd>
        </div>
        <div className={`rounded p-3 ${zaehler.nicht_erzeugbar > 0 ? 'bg-red-50' : 'bg-gray-50'}`}>
          <dt className="text-gray-500">Nicht erzeugbar</dt>
          <dd className={`text-lg font-semibold ${zaehler.nicht_erzeugbar > 0 ? 'text-red-700' : ''}`}>{zaehler.nicht_erzeugbar}</dd>
        </div>
      </dl>

      <section aria-label="Beispiel-Empfänger" className="space-y-2">
        <h3 className="font-medium text-gray-800">Vorschau mit {vorschau.zufaellig.length} zufälligen Empfängern</h3>
        {vorschau.zufaellig.length === 0 && (
          <p className="text-sm text-gray-500">Kein erzeugbares Schreiben — bitte Angaben oder Empfängerkreis prüfen.</p>
        )}
        <ul className="space-y-2">
          {vorschau.zufaellig.map(e => (
            <li key={e.schreiben_id} className="border border-gray-200 rounded-lg p-3 space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span className="font-medium">{e.empfaenger}</span>
                {e.einheit_nr && <span className="text-gray-500">Einheit {e.einheit_nr}</span>}
                <span className="text-gray-500">{e.betreff}</span>
                <button type="button" className="ml-auto text-primary-600 hover:underline"
                  onClick={() => setOffen(o => (o === e.schreiben_id ? null : e.schreiben_id))}>
                  {offen === e.schreiben_id ? 'Vorschau ausblenden' : `PDF-Vorschau ${e.empfaenger}`}
                </button>
              </div>
              {offen === e.schreiben_id && (
                <PdfAnzeige titel={`Vorschau ${e.empfaenger}`} dateiname={`${e.nummer}.pdf`}
                  laden={() => schreibenApi.pdf(e.schreiben_id)} hoehe="h-[60vh]" />
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Nicht erzeugbare Schreiben" className="space-y-2">
        <h3 className="font-medium text-gray-800">Nicht erzeugbare Schreiben</h3>
        {nichtErzeugbar.length === 0 ? (
          <p className="text-sm text-gray-500">Alle Schreiben sind erzeugbar.</p>
        ) : (
          <>
            <p className="text-sm text-gray-600">
              Diese Schreiben werden bei der Freigabe übersprungen; sie bleiben im Postausgang unter „Nicht erzeugbar“.
            </p>
            <div className="border border-red-200 rounded-lg overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-red-50 text-left text-gray-600">
                  <tr>
                    <th className="px-3 py-2">Nummer</th>
                    <th className="px-3 py-2">Empfänger</th>
                    <th className="px-3 py-2">Einheit</th>
                    <th className="px-3 py-2">Ursache</th>
                  </tr>
                </thead>
                <tbody>
                  {nichtErzeugbar.map(n => (
                    <tr key={n.schreiben_id} className="border-t border-red-100">
                      <td className="px-3 py-2 font-mono text-xs">{n.nummer}</td>
                      <td className="px-3 py-2">{n.empfaenger}</td>
                      <td className="px-3 py-2">{n.einheit_nr || '–'}</td>
                      <td className="px-3 py-2 text-red-700">{n.ursache}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
