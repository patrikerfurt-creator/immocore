import client from './client'

export interface VsInfo {
  code: string
  bezeichnung: string
  kategorie: 'stamm_direkt' | 'stamm_kopf' | 'verbrauch'
  wirtschaftsjahre: Array<{ id: string; jahr: number; status: string }>
}

export interface ImportZeile {
  einheit_nr: string
  bezeichnung: string
  alter_wert: string | null
  neuer_wert: string | null
  status: 'neu' | 'geaendert' | 'unveraendert' | 'leer' | 'ungueltig'
  fehler: string | null
  warnung: string | null
}

export interface ImportVorschau {
  preview_token: string
  vs_code: string
  wj_jahr: number | null
  dateiname: string
  zeilen: ImportZeile[]
  warnungen: string[]
  fehler: string[]
  hat_fehler: boolean
  zusammenfassung: Record<string, number>
}

export interface ProtokolEintrag {
  id: string
  vs_code: string
  dateiname: string
  wj_jahr: number | null
  anzahl_aktualisiert: number
  importiert_am: string
  importiert_von: string
}

export const verteilerApi = {
  aktiveVs: (objektId: string): Promise<VsInfo[]> =>
    client.get(`/objekte/${objektId}/verteiler/aktive-vs/`).then(r => r.data),

  exportZip: (objektId: string, vsCodes: Array<{ code: string; wj_id?: string }>): Promise<Blob> =>
    client.post(
      `/objekte/${objektId}/verteiler/export/`,
      { vs_codes: vsCodes },
      { responseType: 'blob' },
    ).then(r => r.data),

  importPreview: (objektId: string, datei: File): Promise<ImportVorschau> => {
    const form = new FormData()
    form.append('datei', datei)
    return client.post(`/objekte/${objektId}/verteiler/import/preview/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  importCommit: (objektId: string, previewToken: string): Promise<{ anzahl_aktualisiert: number }> =>
    client.post(`/objekte/${objektId}/verteiler/import/commit/`, { preview_token: previewToken })
      .then(r => r.data),

  protokoll: (objektId: string): Promise<ProtokolEintrag[]> =>
    client.get(`/objekte/${objektId}/verteiler/protokoll/`).then(r => r.data),
}
