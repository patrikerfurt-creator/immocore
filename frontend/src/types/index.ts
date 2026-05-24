// ── Auth ──────────────────────────────────────────────────────────────
export interface TokenPair {
  access: string
  refresh: string
}

export interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
}

// ── Paginierung ───────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ── Objekte ───────────────────────────────────────────────────────────
export type ObjektTyp = 'WEG' | 'ZH' | 'SEV'
export type ObjektStatus = 'aktiv' | 'archiviert'

export interface ObjektListEingang {
  id: string
  bezeichnung: string
  strasse: string
  plz: string
  ort: string
}

export interface ObjektList {
  id: string
  objektnummer: string
  bezeichnung: string
  kurzbezeichnung: string
  objekt_typ: ObjektTyp
  strasse: string
  plz: string
  ort: string
  status: ObjektStatus
  eingaenge: ObjektListEingang[]
}

export interface Eingang {
  id: string
  objekt: string
  strasse: string
  plz: string
  ort: string
  ist_hauptadresse: boolean
}

export interface Bankkonto {
  id: string
  objekt: string
  konto_typ: 'bewirtschaftung' | 'ruecklage'
  bezeichnung: string
  iban: string
  bic: string
  kontoinhaber: string
  reihenfolge: number
  aktiv: boolean
}

export interface Einheit {
  id: string
  objekt: string
  eingang: string | null
  eingang_bezeichnung: string | null
  flaechennummer: string
  einheit_nr: string
  einheit_typ: string
  lage: string
  umsatzsteuer_abrechnungsart: 'brutto' | 'netto' | null
}

export interface Objekt extends ObjektList {
  baujahr: number | null
  verwaltung_seit: string
  wirtschaftsjahr_start: number
  zahlungsfreigabe_grenzen: Array<{ bis: number | null; rolle: string; frist_tage: number; beschreibung: string }>
  umsatzsteuer_pflichtig: boolean
  glaeubiger_id: string
  eingaenge: Eingang[]
  bankkonten: Bankkonto[]
  einheiten: Einheit[]
}

// ── Personen ──────────────────────────────────────────────────────────
export type PersonTyp = 'eigentuemer' | 'mieter' | 'lieferant' | 'sonstiges'

export interface PersonList {
  id: string
  personennummer: string
  name: string
  person_typ: PersonTyp
  ist_firma: boolean
  email: string
  telefon: string
}

export interface Person extends PersonList {
  vorname: string
  nachname: string
  vorname2: string
  nachname2: string
  briefanrede: string
  briefanrede2: string
  firmenname: string
  strasse: string
  plz: string
  ort: string
  adresse: string
  ibans: string[]
}

export interface HausgeldHistorie {
  id: string
  eigentumsverhaeltnis: string
  betrag: string
  gueltig_ab: string
  kontoart: string
  erstellt_von: number
}

export interface EigentumsVerhaeltnis {
  id: string
  person: string
  person_name: string
  einheit: string
  einheit_nr: string
  beginn: string
  ende: string | null
  hausgeld_soll: string | null
  ist_aktiv: boolean
  hausgeld_historie: HausgeldHistorie[]
}

export interface VerteilerschluesselWert {
  id: string
  schluessel: string
  einheit: string
  einheit_nr: string
  wert: string
}

export interface Verteilerschluessel {
  id: string
  objekt: string
  schluessel: string
  bezeichnung: string
  vs_typ: 'flaeche' | 'mea' | 'kopf' | 'direkt' | 'verbrauch' | null
  aktiv: boolean
  schluessel_typ: string
  einheit: string
  reihenfolge: number
  summe: string | null
  werte: VerteilerschluesselWert[]
}

// ── Buchhaltung ───────────────────────────────────────────────────────
export type BuchungStatus = 'entwurf' | 'festgeschrieben' | 'storniert'

export interface Buchungsart {
  id: string
  nr: string
  kuerzel: string
  bezeichnung: string
  einzelabrechnung: 'ja' | 'nein' | 'anteilig'
  gesamtabrechnung: boolean
  ruecklagen_relevant: boolean
  umlage: 'pflicht' | 'optional' | 'gesperrt'
  beleg_pflicht: boolean
  beschluss_pflicht: boolean
  vier_augen_schwelle: string | null
  sperre_nach_jahresabschluss: boolean
  system_buchungsart: boolean
  aktiv: boolean
}

export interface BuchungList {
  id: string
  buchungsdatum: string
  betrag: string
  belegnr: string
  soll_konto_nr: string
  haben_konto_nr: string
  buchungstext: string
  verwendungszweck: string
  buchungsart_kuerzel: string | null
  status: BuchungStatus
}

export interface Buchung extends BuchungList {
  objekt: string
  buchungsart: string | null
  soll_konto: string
  haben_konto: string
  soll_konto_nr: string
  soll_konto_name: string
  haben_konto_nr: string
  haben_konto_name: string
  unterkonto: string | null
  belegdatum: string | null
  wertstellungsdatum: string | null
  wirtschaftsjahr: number | null
  kostenstelle: string
  beleg_referenz: string
  storno_von: string | null
  erstellt_am: string
}

export interface OffenerPosten {
  id: string
  buchung: string
  personenkonto: string
  eigentuemer_name: string
  einheit_nr: string
  betrag_ursprung: string
  betrag_offen: string
  faellig_ab: string
  status: 'offen' | 'teilverrechnet' | 'verrechnet' | 'storniert' | 'forderungsfall'
  mahnstufe: number
  mahnsperre_bis: string | null
}

// ── Mitarbeiter ───────────────────────────────────────────────────────
export type Abteilung =
  | 'objektmanagement' | 'buchhaltung' | 'frontoffice' | 'backoffice'
  | 'fm_management' | 'geschaeftsfuehrer' | 'prokurist' | 'auszubildender'

export const ABTEILUNG_LABELS: Record<Abteilung, string> = {
  objektmanagement:  'Objektmanagement',
  buchhaltung:       'Buchhaltung',
  frontoffice:       'Frontoffice',
  backoffice:        'Backoffice',
  fm_management:     'FM-Management',
  geschaeftsfuehrer: 'Geschäftsführer',
  prokurist:         'Prokurist',
  auszubildender:    'Auszubildender',
}

export interface MitarbeiterZuordnung {
  id: number
  mitarbeiter_id: number
  vollname: string
  email: string
  abteilungen: Abteilung[]
  aufgabe: Abteilung | ''
}

export interface Mitarbeiter {
  id: string
  vorname: string
  nachname: string
  vollname: string
  email: string
  username: string
  abteilungen: Abteilung[]
  telefon: string
  aktiv: boolean
  eingetreten_am: string | null
  erstellt_am?: string
}

export interface SEPAMandat {
  id: string
  mandatsreferenz: string
  iban: string
  bic: string
  unterzeichnet_am: string
  aktiv: boolean
}

export interface PersonenkontoSaldo {
  id: string
  kontonummer: string
  eigentuemer_id: string
  eigentuemer_name: string
  eigentuemer_ibans: string[]
  einheit_nr: string
  status: 'aktiv' | 'archiviert'
  saldo_offen: number
  sepa_mandat: SEPAMandat | null
}

export interface KontoauszugPosition {
  id: string
  bu_nr: string
  buchungsdatum: string
  buchungstext: string
  soll: number | null
  haben: number | null
  saldo: number
  hat_detail: boolean
}

export interface BuchungDetailPosition {
  id: string
  soll_unterkonto: string | null       // z.B. "0001.900"
  soll_unterkonto_bezeichnung: string
  haben_konto: string                  // z.B. "41900"
  haben_konto_name: string
  ba: string
  betrag: number
}

export interface BuchungDetail {
  bu_nr: string
  buchungsdatum: string
  gesamt_betrag: number
  positionen: BuchungDetailPosition[]
}

export interface Kontoauszug {
  personenkonto: {
    id: string
    kontonummer: string
    eigentuemer_name: string
    einheit_nr: string
    status: string
  }
  saldo_gesamt: number
  positionen: KontoauszugPosition[]
}

export interface BebuchtesKonto {
  id: string
  kontonummer: string
  kontoname: string
  kontoart: string
  abrechnungsart: string
  soll_summe: number
  haben_summe: number
  saldo: number
}

export interface SachkontoAuszugPosition {
  id: string
  bu_nr: string
  buchungsdatum: string
  buchungstext: string
  gegenkonto: string
  soll: number | null
  haben: number | null
  saldo: number
}

export interface SachkontoAuszug {
  konto: { id: string; kontonummer: string; kontoname: string }
  saldo_gesamt: number
  positionen: SachkontoAuszugPosition[]
}

export interface SollstellungsLauf {
  id: string
  objekt: string
  periode_von: string
  periode_bis: string
  trigger: 'automatisch' | 'manuell'
  status: 'simulation' | 'ausstehend' | 'freigegeben' | 'ausgefuehrt' | 'fehler'
  ba_filter: string[]
  anzahl_buchungen: number
  gesamt_summe: string
  freigabe_user: number | null
  freigabe_am: string | null
  ausgefuehrt_von: number
  erstellt_am: string
  fehler_log: unknown[]
}

export interface Sollstellung {
  id: string
  lauf: string
  personenkonto: string
  buchungsart: string
  buchungsart_kuerzel: string
  eigentuemer_name: string
  buchung: string | null
  betrag: string
  periode_monat: number
  periode_jahr: number
  status: 'vorschau' | 'gebucht' | 'fehler' | 'storniert'
}

export interface CamtImportEinstellung {
  id: string
  import_ordner: string
  archiv_ordner: string
  fehler_ordner: string
  poll_intervall_sek: number
  datei_muster: string
  aktiv: boolean
  zuletzt_geprueft_am: string | null
  letzter_import_am: string | null
  letzter_import_datei: string
}

export interface CamtImportLog {
  id: string
  zeitpunkt: string
  import_ordner: string
  anzahl_dateien: number
  anzahl_importiert: number
  anzahl_duplikate: number
  anzahl_erkannt: number
  anzahl_fehler: number
  fehler_details: { datei: string; meldung: string }[]
}

export interface Kontoumsatz {
  id: string
  objekt: string
  bankkonto: string | null
  sha256_hash: string
  betrag: string
  buchungsdatum: string
  wertstellungsdatum: string | null
  auftraggeber_name: string
  auftraggeber_iban: string
  empfaenger_iban: string
  verwendungszweck: string
  status: 'importiert' | 'erkannt' | 'manuell' | 'gebucht' | 'ignoriert'
  buchung: string | null
  ki_vorschlag: Record<string, unknown> | null
  importiert_am: string
}

export interface Mahnlauf {
  id: string
  objekt: string
  trigger: 'automatisch' | 'manuell'
  status: 'simulation' | 'ausstehend' | 'freigegeben' | 'ausgefuehrt' | 'fehler'
  erstellt_am: string
  anzahl_mahnungen: number
  gesamt_gebuehren: string
  gesamt_zinsen: string
}

export interface Mahnung {
  id: string
  lauf: string
  personenkonto: string
  eigentuemer_name: string
  mahnstufe: number
  offene_posten_summe: string
  gebuehr: string
  zinsen: string
  versandt_am: string | null
}

export interface Mahnsperre {
  id: string
  personenkonto: string
  gesperrt_bis: string
  grund: string
  gesetzt_am: string
  aufgehoben_am: string | null
}

export interface Forderungsfall {
  id: string
  personenkonto: string
  eigentuemer_name: string
  objekt: string
  status: string
  eroeffnet_am: string
  hauptforderung: string
  mahngebuehren: string
  verzugszinsen: string
  anwaltskosten: string
  gerichtskosten: string
  gv_kosten: string
  gesamtforderung: string
  beschluss_referenz: string
  notizen: string
  abgeschlossen_am: string | null
}

export interface Basiszinssatz {
  id: string
  gueltig_ab: string
  satz: string
  quelle: string
}

export interface RAPPosition {
  id: string
  objekt: string
  bezeichnung: string
  rap_typ: 'ARAP' | 'PRAP'
  gesamtbetrag: string
  zeitraum_von: string
  zeitraum_bis: string
  soll_konto: string
  haben_konto: string
  status: 'aktiv' | 'aufgeloest'
  erstellt_am: string
}

export interface RAPAufloesung {
  id: string
  position: string
  buchungsdatum: string
  betrag: string
  buchung: string | null
  status: 'geplant' | 'gebucht'
}

export interface BankImport {
  id: string
  objekt: string
  dateiname: string
  importiert_am: string
  anzahl_transaktionen: number
  status: string
  ki_vorschlag: Record<string, unknown>
}

export interface Abrechnungsart {
  id: string
  objekt: string
  code: string
  bezeichnung: string
  aktiv: boolean
}

export interface Konto {
  id: string
  objekt: string
  kontonummer: string
  kontoname: string
  abrechnungsart: string | null
  direktes_buchen: boolean
  verteilerschluessel: string | null
  kontoart: 'standard' | 'summierung' | 'unterkonto'
  arge_konto: boolean
  arge_kostenart: string | null
  aktiv: boolean
}

// ── Rechnungen ────────────────────────────────────────────────────────
export interface Kreditor {
  id: string
  kreditorennummer: string
  name: string
  name_normalisiert: string
  iban: string | null
  bic: string
  strasse: string
  plz: string
  ort: string
  telefon: string
  email: string
  aktiv: boolean
  erstellt_am: string
  rechnungen_anzahl: number
}

export interface DublettKandidat {
  id: string
  name: string
  kreditorennummer: string
  iban: string
  score: number
  match_typ: 'iban' | 'name_exakt' | 'name_fuzzy'
}

export type RechnungStatus =
  | 'importiert' | 'duplikat' | 'prueffall'
  | 'erfasst'
  | 'erkannt' | 'pruefung_match' | 'nicht_erkannt'
  | 'in_pruefung' | 'freigegeben'
  | 'gebucht' | 'bezahlt' | 'abgelehnt' | 'fehler'

export interface RechnungList {
  id: string
  dateiname: string
  rechnungsnummer: string
  kreditor_name: string
  lieferant_name: string
  betrag_brutto: string | null
  waehrung: string
  rechnungsdatum: string | null
  faelligkeitsdatum: string | null
  status: RechnungStatus
  duplikat_typ: string
  duplikat_von_dateiname: string | null
  erstellt_am: string
  objekt_id: string | null
  objekt_bezeichnung: string | null
  kundennummer: string
  vorgeschlagenes_konto_id: string | null
  vorgeschlagenes_konto_label: string | null
  kostenstelle_id: string | null
  kostenstelle_label: string | null
  // Erkennungs-Pipeline v1.3
  erkennungs_stufe: '1' | '2' | '3' | null
  erkennungs_konfidenz: { kreditor: number; objekt: number; aufwandskonto: number } | null
  aufwandskonto_id: string | null
  aufwandskonto_label: string | null
  zugewiesen_an_id: string | null
  zugewiesen_an_name: string | null
  routing_ziel: 'limit_workflow' | 'objektbetreuer' | 'frontoffice' | null
  leistungstext: string
  lock_user: string | null
}

export interface Freigabe {
  id: string
  rechnung: string
  bearbeiter_name: string
  rolle: string
  entscheidung: 'freigegeben' | 'abgelehnt'
  begruendung: string
  zeitstempel: string
}

export interface Rechnung extends RechnungList {
  objekt: string | null
  kreditor: string | null
  kreditor_name: string
  lieferant: string | null
  lieferant_iban: string
  pfad: string | null
  betrag_netto: string | null
  mwst_satz: string | null
  leistungsbeschreibung: string
  textauszug: string
  verarbeitungsnotiz: string
  pdf_upload: string | null
  ki_extraktion: Record<string, unknown> | null
  freigaben: Freigabe[]
  erstellt_am: string
  darf_direkt_freigeben: boolean
  match_regel: string | null
  // OP-Buchung
  aufwandskonto: string | null
  op_buchung: string | null
  aufwand_buchung: string | null
}

export interface RechnungsMatchRegel {
  id: string
  kreditor: string
  kreditor_name: string
  objekt: string
  objekt_bezeichnung: string
  leistungstext_hash: string
  leistungstext_sample: string
  aufwandskonto: string
  aufwandskonto_label: string
  status: 'aktiv' | 'veraltet'
  trefferzahl: number
  erstellt_durch: string
  erstellt_durch_name: string
  erstellt_aus: 'pruefung' | 'freigabe_korrektur' | 'manuell'
  erstellt_am: string
  letzte_anwendung: string | null
}

// ── Prozesse ──────────────────────────────────────────────────────────
export type ProzessTyp = 'objekt_anlegen' | 'eigentuemerwechsel' | 'jahresabrechnung' | 'mieterwechsel'
export type ProzessStatus = 'aktiv' | 'abgeschlossen' | 'abgebrochen'

export interface Prozess {
  id: string
  prozess_typ: ProzessTyp
  prozess_typ_display: string
  objekt: string | null
  current_step: number
  steps_data: Record<string, unknown>
  status: ProzessStatus
  gestartet_am: string
  abgeschlossen_am: string | null
}

export interface ProzessSchritt {
  schritt: number
  bezeichnung: string
  felder: SchritFeld[]
}

export interface SchritFeld {
  name: string
  label: string
  typ: 'text' | 'number' | 'date' | 'select' | 'boolean'
  pflichtfeld: boolean
  optionen?: { value: string; label: string }[]
}

// ── Dokumente ─────────────────────────────────────────────────────────
export interface Dokument {
  id: string
  objekt: string
  dateiname: string
  kategorie: string
  datei: string
  hochgeladen_am: string
  beschreibung: string
}

// ── Tickets ───────────────────────────────────────────────────────────
export type TicketTyp = 'maengelmeldung' | 'anfrage' | 'aufgabe' | 'sonstiges'
export type TicketStatus = 'offen' | 'in_bearbeitung' | 'erledigt' | 'geschlossen'
export type TicketPrioritaet = 'niedrig' | 'mittel' | 'hoch' | 'kritisch'

export interface TicketList {
  id: string
  titel: string
  ticket_typ: TicketTyp
  status: TicketStatus
  prioritaet: TicketPrioritaet
  objekt: string
  erstellt_am: string
}

export interface Ticket extends TicketList {
  einheit: string | null
  beschreibung: string
  zuweisung: number | null
  aktualisiert_am: string
}

// ── Zahlungsverkehr ─────────────────────────────────────────────────
export interface LastschriftPosition {
  betrag: number | string
  personenkonto_id: string
  personenkonto_nr: string
  schuldner_name: string
  schuldner_iban: string
  schuldner_bic: string
  mandatsreferenz: string
  mandat_datum: string
  verwendungszweck: string
  faelligkeitsdatum: string
  seq_typ: 'FRST' | 'RCUR'
  // Nach XML-Erzeugung gefüllt:
  buchung_id?: string
  belegnr?: string
  opos_ausgeglichen?: number
}

export interface OhneMandat {
  person_name?: string
  sollstellung_id: string
  grund: string
}

export interface LastschriftLauf {
  id: string
  objekt: string
  objekt_bezeichnung: string
  sollstellungs_lauf: string | null
  sollstellungs_lauf_info: {
    id: string
    periode_von: string
    periode_bis: string
    status: string
  } | null
  bezeichnung: string
  faelligkeitsdatum: string
  status: 'erstellt' | 'exportiert' | 'eingereicht'
  erstellt_am: string
  erstellt_von: number
  erstellt_von_name: string
  anzahl_positionen: number
  gesamt_summe: string
  positionen: LastschriftPosition[]
  ohne_mandat: OhneMandat[]
  buchungen_erstellt: boolean
  buchungen_datum: string | null
}
