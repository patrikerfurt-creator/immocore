import client from './client'
import type {
  VorgangAntwortVorschlag,
  VorgangCreatePayload,
  VorgangDetail,
  VorgangDokumentUploadErgebnis,
  VorgangList,
  VorgangPortalAnsicht,
  VorgangTyp,
} from '../types'

export const vorgaengeApi = {
  list: (params?: Record<string, string>) =>
    client.get<VorgangList[]>('/vorgaenge/', { params }).then(r => r.data),
  get: (id: string) => client.get<VorgangDetail>(`/vorgaenge/${id}/`).then(r => r.data),
  create: (data: VorgangCreatePayload) =>
    client.post<VorgangDetail>('/vorgaenge/', data).then(r => r.data),

  statusWechseln: (id: string, statusWert: string, kommentar?: string, wiedervorlage_am?: string) =>
    client.post<VorgangDetail>(`/vorgaenge/${id}/status/`, {
      status: statusWert, kommentar, wiedervorlage_am,
    }).then(r => r.data),

  // sichtbarFuerEigentuemer default false (Patrik-Entscheidung): ein Kommentar
  // ist ohne bewusstes Anhaken IMMER rein intern.
  kommentieren: (id: string, text: string, sichtbarFuerEigentuemer = false) =>
    client.post<VorgangDetail>(`/vorgaenge/${id}/kommentar/`, {
      text, sichtbar_fuer_eigentuemer: sichtbarFuerEigentuemer,
    }).then(r => r.data),

  zuweisen: (id: string, userId: number | null) =>
    client.post<VorgangDetail>(`/vorgaenge/${id}/zuweisen/`, { user_id: userId }).then(r => r.data),

  portalSichtbarSetzen: (id: string, sichtbar: boolean) =>
    client.post<VorgangDetail>(`/vorgaenge/${id}/portal-sichtbar/`, { portal_sichtbar: sichtbar }).then(r => r.data),

  // Mitarbeiter-Vorschau ("was sieht der Eigentümer?") — es gibt (noch) kein
  // Eigentümer-Portal, dieser Endpunkt liegt hinter IsAuthenticated.
  portalVorschau: (id: string) =>
    client.get<VorgangPortalAnsicht>(`/vorgaenge/${id}/portal-vorschau/`).then(r => r.data),

  dokumentHochladen: (id: string, file: File, kategorie?: string, beschreibung?: string) => {
    const form = new FormData()
    form.append('datei', file)
    if (kategorie) form.append('kategorie', kategorie)
    if (beschreibung) form.append('beschreibung', beschreibung)
    return client.post<VorgangDokumentUploadErgebnis>(`/vorgaenge/${id}/dokumente/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  typenListe: () => client.get<VorgangTyp[]>('/vorgang-typen/').then(r => r.data),

  antwortVorschlagGenerieren: (id: string) =>
    client.post<VorgangAntwortVorschlag>(`/vorgaenge/${id}/antwort-vorschlag/`).then(r => r.data),

  antwortVorschlagBearbeiten: (id: string, text: string) =>
    client.patch<VorgangAntwortVorschlag>(`/vorgaenge/${id}/antwort-vorschlag/`, { text }).then(r => r.data),

  antwortVorschlagFreigeben: (id: string) =>
    client.post<VorgangAntwortVorschlag>(`/vorgaenge/${id}/antwort-vorschlag/freigeben/`).then(r => r.data),

  antwortVorschlagVerwerfen: (id: string, grund?: string) =>
    client.post<VorgangAntwortVorschlag>(`/vorgaenge/${id}/antwort-vorschlag/verwerfen/`, grund ? { grund } : {}).then(r => r.data),
}

export const vorgangTypenAdminApi = {
  list: () => client.get<VorgangTyp[]>('/vorgang-typen/admin/').then(r => r.data),
  create: (data: Partial<VorgangTyp>) =>
    client.post<VorgangTyp>('/vorgang-typen/admin/', data).then(r => r.data),
  update: (id: string, data: Partial<VorgangTyp>) =>
    client.patch<VorgangTyp>(`/vorgang-typen/admin/${id}/`, data).then(r => r.data),
}
