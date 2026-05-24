import client from './client'
import type {
  Abrechnungsart, Buchung, BuchungList, BankImport, Konto,
  Buchungsart, OffenerPosten,
  CamtImportEinstellung, CamtImportLog, Kontoumsatz,
  BankBuchung, BankMatchRegel, KreditorOP,
  Mahnlauf, Mahnung, Mahnsperre,
  Forderungsfall, Basiszinssatz,
  RAPPosition, RAPAufloesung,
  PersonenkontoSaldo, Kontoauszug, BuchungDetail,
  BebuchtesKonto, SachkontoAuszug,
  HausgeldSollstellungslauf, HausgeldSimulationVorschau,
  AutoLaufProtokoll, AutoPipelineEinstellungen,
} from '../types'

export const buchhaltungApi = {
  // Buchungsarten (BA-Katalog)
  buchungsarten: () =>
    client.get<Buchungsart[]>('/buchungsarten/').then(r => r.data),
  buchungsartenManuell: (buchungstyp?: string) =>
    client.get<Buchungsart[]>('/buchungsarten/manuell-waehlbar/', {
      params: buchungstyp ? { buchungstyp } : undefined,
    }).then(r => r.data),

  // Buchungsstapel
  stapelListe: (params?: Record<string, string>) =>
    client.get('/buchungsstapel/', { params }).then(r => r.data),
  stapelAnlegen: (objekt: string, bezeichnung?: string) =>
    client.post('/buchungsstapel/', { objekt, bezeichnung: bezeichnung ?? '' }).then(r => r.data),
  stapelAusbuchen: (id: string) =>
    client.post(`/buchungsstapel/${id}/ausbuchen/`).then(r => r.data),

  // Buchungsjournal
  buchungen: (params?: Record<string, string>) =>
    client.get<BuchungList[]>('/buchungen/', { params }).then(r => r.data),
  getBuchung: (id: string) => client.get<Buchung>(`/buchungen/${id}/`).then(r => r.data),
  createBuchung: (data: Partial<Buchung>) => client.post<Buchung>('/buchungen/', data).then(r => r.data),
  updateBuchung: (id: string, data: Partial<Buchung>) =>
    client.patch<Buchung>(`/buchungen/${id}/`, data).then(r => r.data),
  festschreiben: (id: string) =>
    client.post(`/buchungen/${id}/festschreiben/`).then(r => r.data),
  stornieren: (id: string) =>
    client.post(`/buchungen/${id}/stornieren/`).then(r => r.data),
  exportCsv: (params?: Record<string, string>) =>
    client.get('/buchungen/export-csv/', { params, responseType: 'blob' }).then(r => r.data),

  // Offene Posten
  offenePosten: (params?: Record<string, string>) =>
    client.get<OffenerPosten[]>('/offene-posten/', { params }).then(r => r.data),

  // Personenkonten / Debitoren
  personenkontenMitSaldo: (objektId: string, params?: { wirtschaftsjahr?: string }) =>
    client.get<PersonenkontoSaldo[]>('/personenkonten/mit-saldo/', { params: { objekt: objektId, ...params } }).then(r => r.data),
  kontoauszug: (personenkontoId: string, params?: { wirtschaftsjahr?: string }) =>
    client.get<Kontoauszug>(`/personenkonten/${personenkontoId}/kontoauszug/`, { params }).then(r => r.data),
  buchungDetail: (personenkontoId: string, buchungId: string) =>
    client.get<BuchungDetail>(`/personenkonten/${personenkontoId}/buchung-detail/`, {
      params: { buchung_id: buchungId },
    }).then(r => r.data),
  zahlungseingang: (personenkontoId: string, data: {
    bank_sachkonto_id: string
    betrag: number
    buchungsdatum: string
    buchungstext?: string
    wirtschaftsjahr_id?: string
  }) =>
    client.post(`/personenkonten/${personenkontoId}/zahlungseingang/`, data).then(r => r.data),

  // Sachkonto-Kontoauszug
  bebuchteKonten: (objektId: string, params?: { wirtschaftsjahr?: string }) =>
    client.get<BebuchtesKonto[]>('/konten/bebuchte/', { params: { objekt: objektId, ...params } }).then(r => r.data),
  sachkontoAuszug: (kontoId: string, params?: { wirtschaftsjahr?: string }) =>
    client.get<SachkontoAuszug>(`/konten/${kontoId}/kontoauszug/`, { params }).then(r => r.data),

  // Hausgeld-Sollstellungen
  hausgeldSollstellungen: (params?: Record<string, string>) =>
    client.get('/hg-sollstellungen/', { params }).then(r => r.data),

  // Hausgeld-Sollstellungsläufe (neue Nebenbuch-Welt)
  hausgeldLaeufe: (objektId?: string, params?: Record<string, string>) =>
    client.get<HausgeldSollstellungslauf[]>('/hg-laeufe/', {
      params: { ...(objektId ? { objekt: objektId } : {}), ...params },
    }).then(r => r.data),
  simulierenHausgeld: (data: { objekt_id: string; periode: string }) =>
    client.post<HausgeldSimulationVorschau>('/hg-laeufe/simulieren/', data).then(r => r.data),
  erstellenHausgeld: (data: { objekt_id: string; periode: string }) =>
    client.post<HausgeldSollstellungslauf>('/hg-laeufe/erstellen/', data).then(r => r.data),
  freigebenHausgeld: (id: string) =>
    client.post<HausgeldSollstellungslauf>(`/hg-laeufe/${id}/freigeben/`).then(r => r.data),
  commitenHausgeld: (id: string) =>
    client.post<HausgeldSollstellungslauf>(`/hg-laeufe/${id}/commiten/`).then(r => r.data),
  stornierenHausgeld: (id: string, grund: string) =>
    client.post<HausgeldSollstellungslauf>(`/hg-laeufe/${id}/stornieren/`, { grund }).then(r => r.data),

  // Auto-Pipeline
  autoPipelineEinstellungen: () =>
    client.get<AutoPipelineEinstellungen>('/auto-lauf-protokolle/einstellungen/').then(r => r.data),
  autoPipelineProtokolle: (params?: { objekt?: string }) =>
    client.get<AutoLaufProtokoll[]>('/auto-lauf-protokolle/', { params }).then(r => r.data),
  autoPipelineProtokoll: (id: string) =>
    client.get<AutoLaufProtokoll>(`/auto-lauf-protokolle/${id}/`).then(r => r.data),
  autoPipelineDownloadPain008: (id: string) =>
    client.get(`/auto-lauf-protokolle/${id}/download-pain008/`, { responseType: 'blob' }).then(r => r.data as Blob),

  // E-Banking CAMT-Einstellungen (global)
  camtEinstellung: () =>
    client.get<CamtImportEinstellung[]>('/camt-einstellungen/')
      .then(r => r.data).then(list => list[0] ?? null),
  camtEinstellungSpeichern: (id: string | null, data: Partial<CamtImportEinstellung>) =>
    id
      ? client.patch<CamtImportEinstellung>(`/camt-einstellungen/${id}/`, data).then(r => r.data)
      : client.post<CamtImportEinstellung>('/camt-einstellungen/', data).then(r => r.data),
  camtVerbindungTesten: (id: string) =>
    client.post(`/camt-einstellungen/${id}/verbindung-testen/`).then(r => r.data),
  camtJetztImportieren: (id: string) =>
    client.post(`/camt-einstellungen/${id}/jetzt-importieren/`).then(r => r.data),
  camtLogs: (limit = 20) =>
    client.get<CamtImportLog[]>('/camt-logs/', { params: { limit } }).then(r => r.data),

  // Import-Ordner-Einstellungen (Rechnungen / Dokumente)
  importOrdnerEinstellung: (bereich: string) =>
    client.get('/import-ordner/', { params: { bereich } })
      .then(r => r.data).then((list: unknown[]) => (list[0] ?? null) as Record<string, string> | null),
  importOrdnerSpeichern: (id: string | null, data: Record<string, unknown>) =>
    id
      ? client.patch(`/import-ordner/${id}/`, data).then(r => r.data)
      : client.post('/import-ordner/', data).then(r => r.data),
  importOrdnerJetztImportieren: (id: string) =>
    client.post(`/import-ordner/${id}/jetzt-importieren/`).then(r => r.data),

  // Kontoumsätze (neue CAMT-Importe)
  kontoumsaetze: (params?: Record<string, string>) =>
    client.get<Kontoumsatz[]>('/kontoumsaetze/', { params }).then(r => r.data),
  camtUpload: (objektId: string, file: File) => {
    const form = new FormData()
    form.append('objekt', objektId)
    form.append('datei', file)
    return client.post('/kontoumsaetze/camt-upload/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  umsatzZuordnen: (id: string, buchungId: string) =>
    client.post(`/kontoumsaetze/${id}/zuordnen/`, { buchung: buchungId }).then(r => r.data),
  umsatzBuchen: (id: string, data: {
    offene_posten_ids?: string[]
    soll_konto_id?: string
    buchungsart?: string
    buchungstext?: string
  }) =>
    client.post(`/kontoumsaetze/${id}/buchen/`, data).then(r => r.data),

  // Mahnwesen
  mahnlaeufe: (objektId?: string) =>
    client.get<Mahnlauf[]>('/mahnlaeufe/', {
      params: objektId ? { objekt: objektId } : undefined,
    }).then(r => r.data),
  mahnlaufSimulieren: (objektId: string) =>
    client.post('/mahnlaeufe/simulieren/', { objekt: objektId }).then(r => r.data),
  mahnlaufAnlegen: (data: Partial<Mahnlauf>) =>
    client.post<Mahnlauf>('/mahnlaeufe/', data).then(r => r.data),
  mahnlaufFreigeben: (id: string) =>
    client.post(`/mahnlaeufe/${id}/freigeben/`).then(r => r.data),
  mahnlaufAusfuehren: (id: string) =>
    client.post(`/mahnlaeufe/${id}/ausfuehren/`).then(r => r.data),
  mahnungen: (laufId: string) =>
    client.get<Mahnung[]>('/mahnungen/', { params: { lauf: laufId } }).then(r => r.data),

  // Mahnsperren
  mahnsperren: (params?: Record<string, string>) =>
    client.get<Mahnsperre[]>('/mahnsperren/', { params }).then(r => r.data),
  mahnsperreSetzen: (data: Partial<Mahnsperre>) =>
    client.post<Mahnsperre>('/mahnsperren/', data).then(r => r.data),
  mahnsperreAufheben: (id: string) =>
    client.post(`/mahnsperren/${id}/aufheben/`).then(r => r.data),

  // Forderungsfälle
  forderungsfaelle: (params?: Record<string, string>) =>
    client.get<Forderungsfall[]>('/forderungsfaelle/', { params }).then(r => r.data),
  forderungsfallAnlegen: (data: Partial<Forderungsfall>) =>
    client.post<Forderungsfall>('/forderungsfaelle/', data).then(r => r.data),
  forderungsfallStatusWechsel: (
    id: string,
    neuerStatus: string,
    beschlussReferenz?: string
  ) =>
    client.post(`/forderungsfaelle/${id}/status-wechsel/`, {
      status: neuerStatus,
      ...(beschlussReferenz ? { beschluss_referenz: beschlussReferenz } : {}),
    }).then(r => r.data),

  // Basiszinssätze
  basiszinssaetze: () =>
    client.get<Basiszinssatz[]>('/basiszinssaetze/').then(r => r.data),
  aktuellerBasiszinssatz: () =>
    client.get('/basiszinssaetze/aktuell/').then(r => r.data),
  zinsenBerechnen: (betrag: number, faelligAb: string, bisDatum: string, typ?: string) =>
    client.post('/basiszinssaetze/zinsen-berechnen/', {
      betrag, faellig_ab: faelligAb, bis_datum: bisDatum,
      schuldner_typ: typ ?? 'verbraucher',
    }).then(r => r.data),

  // RAP / ARAP / PRAP
  rapPositionen: (objektId?: string) =>
    client.get<RAPPosition[]>('/rap-positionen/', {
      params: objektId ? { objekt: objektId } : undefined,
    }).then(r => r.data),
  rapPositionAnlegen: (data: Partial<RAPPosition>) =>
    client.post<RAPPosition>('/rap-positionen/', data).then(r => r.data),
  rapAufloesungen: (positionId: string) =>
    client.get<RAPAufloesung[]>('/rap-aufloesungen/', {
      params: { position: positionId },
    }).then(r => r.data),

  // Kontenplan
  konten: (objektId: string, params?: { wirtschaftsjahr?: string; direktes_buchen?: boolean }) =>
    client.get<Konto[]>('/konten/', { params: { objekt: objektId, ...params } }).then(r => r.data),
  getKonto: (id: string) =>
    client.get<Konto>(`/konten/${id}/`).then(r => r.data),
  createKonto: (data: Partial<Omit<Konto, 'id'>>) =>
    client.post<Konto>('/konten/', data).then(r => r.data),
  updateKonto: (id: string, data: Partial<Konto>) =>
    client.patch<Konto>(`/konten/${id}/`, data).then(r => r.data),
  deleteKonto: (id: string) =>
    client.delete(`/konten/${id}/`),
  vorlageAnlegen: (objektId: string) =>
    client.post('/konten/vorlage-anlegen/', { objekt: objektId }).then(r => r.data),

  // Abrechnungsarten
  abrechnungsarten: (objektId: string) =>
    client.get<Abrechnungsart[]>('/abrechnungsarten/', { params: { objekt: objektId } }).then(r => r.data),
  createAbrechnungsart: (data: Omit<Abrechnungsart, 'id'>) =>
    client.post<Abrechnungsart>('/abrechnungsarten/', data).then(r => r.data),
  updateAbrechnungsart: (id: string, data: Partial<Abrechnungsart>) =>
    client.patch<Abrechnungsart>(`/abrechnungsarten/${id}/`, data).then(r => r.data),
  deleteAbrechnungsart: (id: string) =>
    client.delete(`/abrechnungsarten/${id}/`),

  // Jahresabrechnungen
  jahresabrechnungen: (objektId?: string) =>
    client.get('/jahresabrechnungen/', {
      params: objektId ? { objekt: objektId } : undefined,
    }).then(r => r.data),
  jahresabrechnungFreigeben: (id: string) =>
    client.post(`/jahresabrechnungen/${id}/freigeben/`).then(r => r.data),
  jahresabrechnungSperren: (id: string) =>
    client.post(`/jahresabrechnungen/${id}/sperren/`).then(r => r.data),

  // E-Banking Phase E — BankBuchungen + BankMatchRegeln
  eBankingBuchungen: (params?: Record<string, string>) =>
    client.get<BankBuchung[]>('/e-banking/bank-buchungen/', { params }).then(r => r.data),
  eBankingBuchung: (id: string) =>
    client.get<BankBuchung>(`/e-banking/bank-buchungen/${id}/`).then(r => r.data),
  eBankingVerbuchen: (id: string, data: {
    buchungs_typ?: 'sachkonto' | 'debitor' | 'kreditor'
    gegenkonto_id?: string
    personenkonto_id?: string
    kreditor_op_id?: string
    kreditor_id?: string
    eigentumsverhaeltnis_id?: string
    notiz?: string
    opt_out_lernen?: boolean
  }) =>
    client.post<BankBuchung>(`/e-banking/bank-buchungen/${id}/verbuchen/`, data).then(r => r.data),
  eBankingSpeichern: (id: string, data: {
    gegenkonto_id?: string | null
    kreditor_id?: string | null
    eigentumsverhaeltnis_id?: string | null
    notiz?: string
  }) =>
    client.post<BankBuchung>(`/e-banking/bank-buchungen/${id}/speichern/`, data).then(r => r.data),
  eBankingErkennungNeu: (id: string) =>
    client.post<BankBuchung>(`/e-banking/bank-buchungen/${id}/erkennung-neu/`).then(r => r.data),
  eBankingStorno: (id: string, begruendung: string) =>
    client.post<BankBuchung>(`/e-banking/bank-buchungen/${id}/storno/`, { begruendung }).then(r => r.data),
  eBankingMatchRegeln: (params?: Record<string, string>) =>
    client.get<BankMatchRegel[]>('/e-banking/bank-match-regeln/', { params }).then(r => r.data),
  eBankingMatchRegelDeaktivieren: (id: string) =>
    client.patch<BankMatchRegel>(`/e-banking/bank-match-regeln/${id}/`, { status: 'veraltet' }).then(r => r.data),
  eBankingKreditorOPs: (params?: { objekt?: string; status?: string }) =>
    client.get<KreditorOP[]>('/e-banking/kreditor-ops/', { params }).then(r => r.data),
  eBankingCamt054Liste: () =>
    client.get('/kontoumsaetze/camt054-liste/').then(r => r.data),
  camtVorschauUpload: (objektId: string, file: File) => {
    const form = new FormData()
    form.append('objekt', objektId)
    form.append('datei', file)
    return client.post<{
      camt_typ: string
      transaktionen: Array<Record<string, unknown>>
      neu_anzahl: number
      duplikat_anzahl: number
      gesamt: number
      import_datei: string
      hinweis?: string
    }>('/kontoumsaetze/camt-vorschau/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  camtDirektImport: (objektId: string, vorschau: {
    transaktionen: Array<Record<string, unknown>>
    import_datei: string
  }) =>
    client.post<{ importiert: number; duplikate: number; erkannt: number; gesamt: number }>(
      '/kontoumsaetze/camt-upload/',
      { objekt: objektId, transaktionen: vorschau.transaktionen, import_datei: vorschau.import_datei }
    ).then(r => r.data),

  // Legacy BankImport
  bankImporte: (params?: Record<string, string>) =>
    client.get<BankImport[]>('/bank-importe/', { params }).then(r => r.data),
  uploadCamtLegacy: (objektId: string, file: File) => {
    const form = new FormData()
    form.append('objekt', objektId)
    form.append('datei', file)
    return client.post('/bank-importe/camt053-upload/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
}
