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
  bezeichnung: string
  strasse: string
  plz: string
  ort: string
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
  zahlungsverkehr: boolean
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

export interface Objekt extends Omit<ObjektList, 'eingaenge'> {
  baujahr: number | null
  verwaltung_seit: string
  wirtschaftsjahr_start: number
  zahlungsfreigabe_grenzen: Array<{ bis: number | null; rolle: string; frist_tage: number; beschreibung: string }>
  umsatzsteuer_pflichtig: boolean
  glaeubiger_id: string
  kurzbezeichnung: string
  auto_pipeline_aktiv: boolean
  bundesland: string
  eingaenge: Eingang[]
  bankkonten: Bankkonto[]
  einheiten: Einheit[]
}

// ── Auto-Pipeline ─────────────────────────────────────────────────────
export type AutoLaufStatus = 'erfolg' | 'teilweise_erfolg' | 'fehler' | 'uebersprungen'

export interface AutoPipelineWarnung {
  ev_id?: string
  name?: string
  einheit?: string
  warnung_typ: string
  nachricht: string
}

export interface AutoLaufProtokoll {
  id: string
  objekt: string
  objekt_bezeichnung: string
  objekt_nummer: string
  ausgefuehrt_am: string
  periode: string
  status: AutoLaufStatus
  sollstellungslauf: string | null
  lastschriftlauf: string | null
  anzahl_evs_geplant: number
  anzahl_evs_erfolgreich: number
  anzahl_evs_uebersprungen: number
  summe_sollstellungen: string
  summe_lastschrift: string
  datei_pfad: string | null
  warnungen: AutoPipelineWarnung[]
  fehler: string | null
}

export interface SepaZahlungslauf {
  id: string
  faelligkeitsdatum: string
  anzahl_rechnungen: number
  summe: string
  dateiname: string
  positionen: { id: string; rechnungsnummer: string; kreditor: string; betrag: string; objekt: string }[]
  buchungs_fehler: string[]
  uebersprungen: string[]
  erstellt_am: string
  erstellt_von: number | null
  erstellt_von_name: string
}

export interface AutoPipelineEinstellungen {
  aktiv: boolean
  stichtag: number
  naechster_lauf: string
  aktive_objekte: number
  sepa_output_dir: string
  vorlauf_bd: number
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
  anrede: string
  vorname: string
  nachname: string
  vorname2: string
  nachname2: string
  briefanrede: string
  briefanrede2: string
  firmenname: string
  adresse: string
  ibans: string[]
}

export interface HausgeldHistorie {
  id: string
  eigentumsverhaeltnis: string
  betrag: string
  gueltig_ab: string
  abrechnungsart_code: string
  wirtschaftsplan_jahr: number | null
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
  hausgeld_eintraege: HausgeldHistorie[]
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
  user_id: number
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
  opos_nr: string | null
  bu_nr: string
  buchungsdatum: string
  buchungstext: string
  soll: number | null
  haben: number | null
  saldo: number
  hat_detail: boolean
  typ?: string
  status?: string | null
  ist_betrag?: number | null
}

export interface BuchungDetailPosition {
  id: string
  soll_unterkonto: string | null       // z.B. "0001.900"
  soll_unterkonto_bezeichnung: string
  haben_konto: string                  // z.B. "41900"
  haben_konto_name: string
  ba: string
  betrag: number
  op_nummer: string | null             // getilgter offener Posten (OPOS-Nr.)
  op_periode: string | null            // Periode der getilgten Sollstellung
  op_status: string | null             // offen | teilbezahlt | ausgeglichen
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


export interface CamtImportEinstellung {
  id: string
  import_ordner: string
  archiv_ordner: string
  fehler_ordner: string
  poll_intervall_sek: number
  datei_muster: string
  aktiv: boolean
  objekt: string | null
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

export type BankBuchungStatus =
  | 'importiert' | 'erkannt' | 'vorschlag' | 'unklar'
  | 'verbucht' | 'storniert'
  // legacy (Altdaten)
  | 'manuell' | 'gebucht' | 'ignoriert' | 'unbekannt'

export interface BankBuchungKontoDetail {
  id: string
  kontonummer: string
  kontoname: string
}

export interface BankBuchungPersonDetail {
  id: string
  name: string
}

export interface BankBuchungEVDetail {
  id: string
  einheit_nr: string
  eigentuemer: string
}

export interface BankErkennungsLog {
  id: string
  stufe_erreicht: string
  quelle: string
  konfidenz: string | null
  auto_verbucht: boolean
  details_json: Record<string, unknown> | null
  erstellt_am: string
}

export interface BankBuchung {
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
  end_to_end_id: string
  status: BankBuchungStatus
  erkannt_gegenkonto: string | null
  erkannt_gegenkonto_detail: BankBuchungKontoDetail | null
  erkannt_eigentumsverhaeltnis: string | null
  erkannt_eigentumsverh_detail: BankBuchungEVDetail | null
  erkannt_kreditor: string | null
  erkannt_kreditor_detail: BankBuchungPersonDetail | null
  erkennungs_quelle: string
  erkennungs_konfidenz: string | null
  erkennungs_begruendung: string
  match_regel: string | null
  buchung: string | null
  verbucht_am: string | null
  verbucht_von: number | null
  verbucht_von_username: string | null
  verbucht_personenkonto_detail: {
    id: string
    nummer: string
    name: string
    einheit_nr: string
  } | null
  notiz: string
  importiert_am: string
  import_datei: string
  erkennungs_log: BankErkennungsLog[]
}

export interface KreditorOP {
  id: string
  op_nummer: number
  betrag_ursprung: string
  betrag_offen: string
  faellig_ab: string
  status: 'offen' | 'teilbezahlt' | 'bezahlt' | 'storniert' | 'ausgebucht'
  kreditor_name: string
  rechnung_nr: string
  betreff: string
  /** Bestimmt beim Ausbuchen die Buchungsseite — serverseitig ermittelt. */
  art: 'forderung' | 'verbindlichkeit'
}

export interface KreditorOPAusbuchungResponse {
  anzahl: number
  wirtschaftsjahr: number
  gegenkonto: string
  summe: string
  summe_verbindlichkeiten: string
  summe_forderungen: string
  ops: Array<{
    op_nummer: number
    kreditor: string
    betrag: string
    art: 'forderung' | 'verbindlichkeit'
    soll_konto: string
    haben_konto: string
    belegnr: string
  }>
}

export interface BankMatchRegel {
  id: string
  bankkonto: string
  bankkonto_iban: string
  kontrahent_iban: string
  verwendungszweck_hash: string
  gegenkonto: string
  gegenkonto_detail: BankBuchungKontoDetail | null
  kreditor: string | null
  eigentumsverhaeltnis: string | null
  status: 'aktiv' | 'veraltet'
  erstellt_aus: 'bestaetigung' | 'korrektur' | 'manuell'
  trefferzahl: number
  letzte_anwendung: string | null
  erstellt_am: string
  erstellt_von: number
  erstellt_von_username: string
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
  wirtschaftsjahr: string | null
  wirtschaftsjahr_jahr: number | null
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
  // Handwerker-Erweiterung (apps.handwerker)
  gewerke: string[]
  gewerke_bezeichnungen: string[]
  ist_handwerker: boolean
  kontakt_person: string
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
  | 'in_buchhaltung' | 'zur_freigabe'                      // v1.1 zweistufig
  | 'in_pruefung' | 'freigegeben'
  | 'teilbezahlt' | 'bezahlt' | 'wkz_beleg' | 'abgelehnt' | 'storniert' | 'fehler'

export type Ampel = 'gruen' | 'gelb' | 'rot'

export interface AmpelFeld {
  wert: unknown
  llm_konfidenz: number
  validierung: 'ok' | 'warnung' | 'fehler' | 'keine'
  hinweis: string
  konfidenz: number
  ampel: Ampel
}

export interface AmpelErgebnis {
  ampel: Ampel
  gesamt_konfidenz: number
  felder: Record<string, AmpelFeld>
}

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
  pruefgrund?: string           // Klartext-Begründung für Prüffall/Duplikat
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
  op_nummer: number | null
  sepa_lastschrift: boolean
  ist_gutschrift: boolean
  // Umbau Rechnungseingang v1.0
  erkennung_ampel: Ampel | null
  erkennung_gesamt_konfidenz: string | null
  betrag_haushaltsnah: string | null
  ist_schlussrechnung: boolean
  skonto_faellig_bis: string | null
  skonto_genutzt: boolean
  kostenverursacher_id: string | null
  erfasst_von_name: string | null
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
  ki_extraktion: Record<string, unknown> | null
  freigaben: Freigabe[]
  erstellt_am: string
  darf_direkt_freigeben: boolean
  darf_freigeben: boolean
  match_regel: string | null
  // OP-Buchung
  aufwandskonto: string | null
  op_buchung: string | null
  aufwand_buchung: string | null
  splits: RechnungSplitPosition[]
  // Umbau Rechnungseingang v1.0
  kostenverursacher: string | null
  kostenverursacher_label: string | null
  betrag_haushaltsnah: string | null
  ist_schlussrechnung: boolean
  skonto_prozent: string | null
  skonto_betrag: string | null
  skonto_faellig_bis: string | null
  skonto_genutzt: boolean
  erkennung_ampel: Ampel | null
  erkennung_gesamt_konfidenz: string | null
  erkennung_details: Record<string, AmpelFeld>
}

export interface RechnungSplitPosition {
  id: string
  aufwandskonto: string        // UUID
  aufwandskonto_label: string
  betrag: string               // Decimal als String
  position: number
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

export type DokumentTyp = 'beleg' | 'vertrag' | 'korrespondenz' | 'beschluss' | 'abrechnung' | 'sonstiges'

export const DOKUMENT_TYP_CHOICES: { value: DokumentTyp; label: string }[] = [
  { value: 'beleg',         label: 'Beleg' },
  { value: 'vertrag',       label: 'Vertrag' },
  { value: 'korrespondenz', label: 'Korrespondenz' },
  { value: 'beschluss',     label: 'Beschluss' },
  { value: 'abrechnung',    label: 'Abrechnung' },
  { value: 'sonstiges',     label: 'Sonstiges' },
]

// Minimale DMS-Leseansicht (Objekt-Dokumentenliste, Spec Abschnitt 7)
export interface ObjektDokument {
  id: string
  dateiname: string
  kategorie: string
  dokument_typ: DokumentTyp
  abgelegt_am: string
  beleg_nummer: string | null
  revisionssicher: boolean
  rechnung_nummer: string | null
  rechnung_id: string | null
}

// ── Vorgänge (Ticket-Ablösung, Spec CLAUDE_CODE_ANLEITUNG_VORGANG_DMS_v1_0) ──
export type VorgangStatus =
  | 'offen' | 'in_bearbeitung' | 'wartet_extern' | 'wiedervorlage' | 'erledigt' | 'storniert'
export type VorgangPrioritaet = 'niedrig' | 'normal' | 'hoch'
export type VorgangQuelle = 'manuell' | 'mail' | 'telefon' | 'beschluss' | 'portal'
export type VorgangEreignisTyp =
  | 'kommentar' | 'statuswechsel' | 'zuweisung_geaendert'
  | 'dokument_verknuepft' | 'system_wiedervorlage_faellig'
  | 'antwort_vorschlag_erzeugt' | 'antwort_vorschlag_bearbeitet'
  | 'antwort_vorschlag_freigegeben' | 'antwort_vorschlag_verworfen'
  | 'handwerker_beauftragt' | 'handwerker_angenommen' | 'handwerker_abgelehnt'
  | 'handwerker_abgeschlossen' | 'handwerker_abgelaufen'

export interface VorgangTyp {
  id: string
  code: string
  bezeichnung: string
  standard_prioritaet: VorgangPrioritaet
  aktiv: boolean
  sortierung: number
  antwort_vorschlag_aktiv: boolean
  erstellt_am: string
  erstellt_von: number | null
}

// ── KI-Antwortvorschlag am Vorgang ─────────────────────────────────────
export type VorgangAntwortVorschlagStatus = 'entwurf' | 'freigegeben' | 'verworfen' | 'fehlgeschlagen'

export interface VorgangAntwortVorschlag {
  id: string
  vorgang: string
  text_ki: string
  text: string
  status: VorgangAntwortVorschlagStatus
  modell: string
  fehler: string
  erzeugt_am: string
  erzeugt_von: number | null
  erzeugt_von_name: string | null
  bearbeitet_am: string | null
  bearbeitet_von: number | null
  bearbeitet_von_name: string | null
  freigegeben_am: string | null
  freigegeben_von: number | null
  freigegeben_von_name: string | null
}

export interface VorgangList {
  id: string
  nummer: string
  typ: string
  typ_bezeichnung: string
  quelle: VorgangQuelle
  objekt: string | null
  objekt_bezeichnung: string | null
  einheit: string | null
  einheit_nr: string | null
  person: string | null
  person_name: string | null
  betreff: string
  status: VorgangStatus
  prioritaet: VorgangPrioritaet
  zugewiesen_an: number | null
  zugewiesen_an_name: string | null
  faellig_am: string | null
  wiedervorlage_am: string | null
  erstellt_am: string
}

export interface VorgangEreignis {
  id: string
  typ: VorgangEreignisTyp
  text: string | null
  alter_wert: string | null
  neuer_wert: string | null
  /** true (Default) = nur intern sichtbar; false = für den Eigentümer sichtbar. */
  intern: boolean
  erstellt_am: string
  erstellt_von: number | null
  erstellt_von_name: string | null
}

export interface VorgangDokument {
  id: string
  dateiname: string
  kategorie: string
  dokument_typ: string
  beschreibung: string
  version: number
  vorgaenger_version: string | null
  sha256: string | null
  hochgeladen_am: string
  hochgeladen_von: number
  hochgeladen_von_name: string | null
}

export interface VorgangDetail extends VorgangList {
  beschreibung: string | null
  mail_referenz: string | null
  telefon_rufnummer: string | null
  portal_sichtbar: boolean
  erstellt_von: number
  erstellt_von_name: string | null
  geschlossen_am: string | null
  geschlossen_von: number | null
  geschlossen_von_name: string | null
  ereignisse: VorgangEreignis[]
  dokumente: VorgangDokument[]
  antwort_vorschlag: VorgangAntwortVorschlag | null
}

export interface VorgangCreatePayload {
  typ: string
  objekt?: string | null
  einheit?: string | null
  person?: string | null
  betreff: string
  beschreibung?: string
  prioritaet?: VorgangPrioritaet
  faellig_am?: string | null
  zugewiesen_an?: number | null
  mail_referenz?: string
  telefon_rufnummer?: string
  portal_sichtbar?: boolean
}

export interface VorgangDokumentUploadErgebnis {
  dokument: VorgangDokument
  duplikat_warnung: boolean
}

/** Antwort von GET /vorgaenge/{id}/portal-vorschau/ — Mitarbeiter-Vorschau
 * ("was sieht der Eigentümer?"). Enthält bewusst KEINE Dokument-ID/-Link und
 * keinen zugewiesenen Mitarbeiter — es gibt (noch) kein Eigentümer-Portal. */
export interface VorgangPortalAnsichtEreignis {
  typ: VorgangEreignisTyp
  typ_anzeige: string
  text: string | null
  erstellt_am: string
}

export type VorgangPortalAnsicht =
  | { sichtbar: false }
  | {
      sichtbar: true
      nummer: string
      betreff: string
      beschreibung: string | null
      status: VorgangStatus
      status_anzeige: string
      erstellt_am: string
      objekt_bezeichnung: string | null
      einheit_nr: string | null
      ereignisse: VorgangPortalAnsichtEreignis[]
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
  hausgeld_sollstellungslauf: string | null
  hausgeld_lauf_info: {
    id: string
    periode: string
    status: string
    anzahl_sollstellungen: number
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

// ── Hausgeld-Nebenbuch ────────────────────────────────────────────────
export interface HausgeldSollstellung {
  id: string
  objekt: string
  eigentumsverhaeltnis: string
  ev_person_name: string | null
  ev_einheit_nr: string | null
  personenkonto_id: string | null
  personenkonto_nr: string | null
  sollstellungs_typ: string
  ba: string | null
  ba_nr: string | null
  periode: string
  faellig_am: string
  opos_nr: string
  soll_betrag: string
  ist_betrag: string
  status: string
  status_cached: string
  storniert_am: string | null
  erstellt_am: string
}

export interface HausgeldSollstellungslauf {
  id: string
  objekt: string
  objekt_bezeichnung: string
  typ: 'hausgeld_monat' | 'sonderumlage' | 'abrechnungsergebnis_jahr'
  periode: string
  status: 'vorschau' | 'freigegeben' | 'commited' | 'storniert'
  wirtschaftsjahr: string | null
  wirtschaftsjahr_jahr: number | null
  anzahl_sollstellungen: number
  summe: string
  erstellt_am: string
  erstellt_von: number
  erstellt_von_name: string | null
  freigabe_user: number | null
  freigabe_user_name: string | null
  freigegeben_am: string | null
  commited_am: string | null
  storniert_am: string | null
  storniert_grund: string
}

export interface HausgeldSimulationsPosition {
  eigentumsverhaeltnis_id: string
  eigentuemer_name: string
  einheit_nr: string
  splits: { ba_code: string; betrag: string }[]
  summe: string
  opos_nr_neu: string
}

export interface HausgeldSimulationVorschau {
  objekt_id: string
  periode: string
  anzahl_evs: number
  gesamtsumme: string
  positionen: HausgeldSimulationsPosition[]
  warnungen: string[]
}

// ── Wirtschaftsjahre ──────────────────────────────────────────────────
export type WirtschaftsjahrStatus = 'offen' | 'abgeschlossen'

export interface Wirtschaftsjahr {
  id: string
  objekt: string
  objekt_nr: string
  objekt_bezeichnung: string
  jahr: number
  beginn_monat: number
  status: WirtschaftsjahrStatus
  vorjahr: string | null
  eroeffnet_am: string
  eroeffnet_von: number | null
  abgeschlossen_am: string | null
  beginn_datum: string
  ende_datum: string
}

export interface EinheitVerbrauch {
  id: string
  wirtschaftsjahr: string
  einheit: string
  vs_code: string
  wert: string | null
  einheit_text: string
  quelle: 'manuell' | 'ablese' | 'rechnung'
}

export interface KontoVerteilerSchluessel {
  id: string
  konto: string
  vs_code: string
  gueltig_ab: string
}

export interface FolgejahrPreviewEintrag {
  objekt_id: string
  objekt_nr: string
  bezeichnung: string
  letztes_wj: { jahr: number; status: string } | null
  folgejahr: number | null
  status: 'ok' | 'fehler'
  fehler: string | null
}

export interface FolgejahrPreviewResponse {
  ergebnisse: FolgejahrPreviewEintrag[]
}

export interface FolgejahrCommitEintrag {
  objekt_id: string
  bezeichnung?: string
  status: 'ok' | 'fehler'
  wj_id?: string
  wj_jahr?: number
  fehler?: string | null
}

export interface FolgejahrCommitResponse {
  ergebnisse: FolgejahrCommitEintrag[]
}

export interface WechselAnalyseSollstellung {
  sollstellung_id: string
  opos_nr: string
  periode: string
  soll_betrag: string
  ist_betrag: string
  bucket: 'stornieren' | 'erstatten'
  lastschrift_juenger_56_tage: boolean
}

export interface WechselAnalyse {
  einheit_id: string
  verkaeufer_ev_id: string
  wirkungs_periode: string
  art: 'zukuenftig' | 'rueckwirkend'
  stornieren: WechselAnalyseSollstellung[]
  erstatten: WechselAnalyseSollstellung[]
  verkaeufer_iban: string | null
  warnung_keine_iban: boolean
  erstattung_summe: string
}

export interface EWAbschlussErgebnis {
  wechsel_id: string
  kaeufer_ev_id: string
  auszahlungslauf_id: string | null
  nachhol_count: number
  storniert_count: number
}

// ── Handwerker (Handwerkerauftrag, Phase D — Spec
// CLAUDE_CODE_ANLEITUNG_HANDWERKERAUFTRAG_v1_0) ────────────────────────
export interface Gewerk {
  id: string
  code: string
  bezeichnung: string
  aktiv: boolean
  sortierung: number
  erstellt_am: string
  erstellt_von: number | null
}

export interface ObjektHandwerker {
  id: string
  objekt: string
  kreditor: string
  kreditor_name: string
  gewerke_bezeichnung: string | null
  prioritaet: number
  notiz: string
  erstellt_am: string
}

export type HandwerkerauftragStatus =
  | 'entwurf' | 'versendet' | 'angenommen' | 'abgelehnt'
  | 'in_arbeit' | 'abgeschlossen' | 'storniert' | 'abgelaufen'

export type HandwerkerauftragEreignisTyp =
  | 'statuswechsel' | 'versand' | 'versand_fehlgeschlagen'
  | 'kommentar' | 'rechnung_zugeordnet' | 'system_abgelaufen'

export interface HandwerkerauftragList {
  id: string
  nummer: string
  titel: string
  status: HandwerkerauftragStatus
  prioritaet: VorgangPrioritaet
  geschaetzte_kosten: string | null
  objekt: string
  objekt_bezeichnung: string | null
  kreditor: string
  kreditor_name: string
  kreditor_gewerke_bezeichnung: string | null
  erstellt_am: string
  versendet_am: string | null
  angenommen_am: string | null
  abgelehnt_am: string | null
  abgeschlossen_am: string | null
  rechnungen_anzahl: number
}

export interface HandwerkerauftragEreignis {
  id: string
  typ: HandwerkerauftragEreignisTyp
  text: string | null
  alter_wert: string | null
  neuer_wert: string | null
  erstellt_am: string
  erstellt_von: number | null
  erstellt_von_name: string | null
}

export interface HandwerkerauftragRechnung {
  id: string
  rechnungsnummer: string
  rechnungsdatum: string | null
  betrag_brutto: string | null
}

export interface HandwerkerauftragTokenStatus {
  gueltig_bis: string
  verbraucht_am: string | null
}

export interface HandwerkerauftragVorgangRef {
  id: string
  nummer: string
  betreff: string
}

export interface HandwerkerauftragDetail {
  id: string
  nummer: string
  titel: string
  beschreibung: string
  status: HandwerkerauftragStatus
  prioritaet: VorgangPrioritaet
  gewuenscht_ab: string | null
  geschaetzte_kosten: string | null
  objekt: string
  objekt_bezeichnung: string | null
  kreditor: string
  kreditor_name: string
  kreditor_gewerke_bezeichnung: string | null
  vorgang: HandwerkerauftragVorgangRef | null
  ablehnung_grund: string
  abschluss_notiz: string
  erstellt_am: string
  erstellt_von: number | null
  erstellt_von_name: string | null
  versendet_am: string | null
  angenommen_am: string | null
  abgelehnt_am: string | null
  abgeschlossen_am: string | null
  geaendert_am: string
  ereignisse: HandwerkerauftragEreignis[]
  rechnungen: HandwerkerauftragRechnung[]
  token_status: HandwerkerauftragTokenStatus | null
}

export interface HandwerkerauftragCreatePayload {
  kreditor: string
  objekt?: string | null
  titel: string
  beschreibung?: string
  gewuenscht_ab?: string | null
  prioritaet?: VorgangPrioritaet
  geschaetzte_kosten?: number | string | null
}

// ── Öffentliche Auftragsbestätigung (kein Login, Token-Link) ───────────
export interface OeffentlicherAuftrag {
  nummer: string
  objekt_bezeichnung: string
  objekt_adresse: string
  titel: string
  beschreibung: string
  prioritaet: VorgangPrioritaet
  gewuenscht_ab: string | null
  geschaetzte_kosten: string | null
  kreditor_name: string
  gueltig_bis: string
  aktion: 'annehmen' | 'ablehnen'
  status: HandwerkerauftragStatus
  bereits_verwendet: boolean
  abgelaufen: boolean
}

export interface OeffentlicherAuftragBestaetigungErgebnis {
  nummer: string
  status: HandwerkerauftragStatus
  aktion: 'annehmen' | 'ablehnen'
}

// ---------------------------------------------------------------------------
// Eigentümerversammlung (Spec v1.1, Phase B)
// ---------------------------------------------------------------------------

export type EVStatus =
  | 'entwurf'
  | 'in_bearbeitung'
  | 'einladungen_versendet'
  | 'durchgefuehrt'
  | 'beschluesse_verarbeitet'
  | 'archiviert'

export type EVArt = 'ordentlich' | 'ausserordentl' | 'wiederholung'
export type EVStimmprinzip = 'kopf' | 'verteilerschluessel'
export type EVVersandkanal = 'portal' | 'email' | 'epost'

export type EVAbstimmungsmodus =
  | 'einfache_mehrheit'
  | 'qualifizierte_mehrheit'
  | 'einstimmigkeit'
  | 'allstimmigkeit'
  | 'kein_beschluss'

export type EVAbstimmungsergebnis =
  | 'offen' | 'angenommen' | 'abgelehnt' | 'vertagt' | 'entfallen'

export interface EVTaskStatusEintrag {
  erledigt: boolean
  bezeichnung: string
}

export interface EVTaskStatus {
  task1: EVTaskStatusEintrag
  task2: EVTaskStatusEintrag
  task3: EVTaskStatusEintrag
  task4: EVTaskStatusEintrag
  task5: EVTaskStatusEintrag
  anzahl_erledigt: number
}

export interface EVLadungsfrist {
  termin: string | null
  tage_bis_termin: number | null
  frist_tage: number
  eingehalten: boolean
  warnung: string
}

export interface Tagesordnungspunkt {
  id: string
  ev: string
  nummer: number
  titel: string
  erlaeuterung: string
  beschlussvorlage: string
  abstimmungsmodus: EVAbstimmungsmodus
  abstimmungsmodus_display: string
  mehrheit_schwelle: string | null
  abstimmung_ja: string
  abstimmung_nein: string
  abstimmung_enthaltung: string
  abstimmungsergebnis: EVAbstimmungsergebnis
  abstimmungsergebnis_display: string
  ergebnis_bemerkung: string
  triggert_vorgang: boolean
  triggert_wirtschaftsplan: boolean
}

export interface TagesordnungspunktCreatePayload {
  ev: string
  titel: string
  nummer?: number | null
  erlaeuterung?: string
  beschlussvorlage?: string
  abstimmungsmodus?: EVAbstimmungsmodus
  mehrheit_schwelle?: string | null
  triggert_vorgang?: boolean
  triggert_wirtschaftsplan?: boolean
}

export interface EVList {
  id: string
  objekt: string
  objekt_bezeichnung: string
  objektnummer: string
  arbeitsname: string
  art: EVArt
  termin: string | null
  ort: string
  status: EVStatus
  status_display: string
  stimmprinzip: EVStimmprinzip
  anzahl_tops: number
  anzahl_teilnehmer: number
  tasks_erledigt: number
  einladung_versendet_am: string | null
  durchgefuehrt_am: string | null
  erstellt_am: string
}

export interface EVDetail {
  id: string
  objekt: string
  objekt_bezeichnung: string
  objektnummer: string
  arbeitsname: string
  art: EVArt
  art_display: string
  termin: string | null
  ort: string
  raum_buchung_notizen: string
  terminvorschlaege: unknown[]
  stimmprinzip: EVStimmprinzip
  stimmprinzip_display: string
  stimm_verteilerschluessel: string | null
  stimm_verteilerschluessel_text: string | null
  stimm_wirtschaftsjahr: number
  status: EVStatus
  status_display: string
  task_status: EVTaskStatus
  ladungsfrist: EVLadungsfrist
  einladungstext: string
  einladungs_pdf: string | null
  einladungs_pdf_dateiname: string | null
  protokoll_pdf: string | null
  tagesordnung: Tagesordnungspunkt[]
  versammlungsleiter: string
  protokollfuehrer: string
  einladung_versendet_am: string | null
  durchgefuehrt_am: string | null
  erstellt_am: string
  erstellt_von: number | null
  erstellt_von_name: string | null
}

export interface EVCreatePayload {
  objekt: string
  arbeitsname?: string
  art?: EVArt
  stimmprinzip?: EVStimmprinzip
  stimm_verteilerschluessel?: string | null
  stimm_wirtschaftsjahr?: number
}

export interface EVTeilnehmerAnteil {
  id: string
  eigentumsverhaeltnis: string
  einheit_nr_snapshot: string
  mea_wert_snapshot: string | null
}

export interface EVTeilnehmer {
  id: string
  ev: string
  person: string
  person_name: string
  stimmkraft: string
  zusage_status: 'offen' | 'zugesagt' | 'abgesagt'
  zusage_am: string | null
  zusage_quelle: string
  ist_anwesend: boolean | null
  anwesenheit_erfasst_am: string | null
  vertreten_durch: string | null
  vertreten_durch_name: string | null
  vertreter_name: string
  vollmacht_dokument: string | null
  anteile: EVTeilnehmerAnteil[]
}

export interface EVStimmkraftErgebnis {
  teilnehmer: number
  neu: number
  entfallen: number
  gesamt_stimmkraft: string
  ohne_stimmrecht: string[]
  grundlage: string
}

export interface EVVersandplanEintrag {
  teilnehmer_id: string
  person_id: string
  name: string
  kanal: EVVersandkanal
  empfaenger: string
  hat_email: boolean
  hat_portalzugang: boolean
  stimmkraft: string
  nicht_stimmberechtigt: boolean
  hinweis: string
}

export interface EVVersandplan {
  ev_id: string
  eintraege: EVVersandplanEintrag[]
  zusammenfassung: Record<EVVersandkanal, number>
  anzahl: number
  ladungsfrist: EVLadungsfrist
  portal_verfuegbar: boolean
  portal_hinweis: string
}

export interface EVVersandErgebnis {
  gesamt: number
  erfolgreich: number
  fehlgeschlagen: number
  uebersprungen: number
  kanaele: Record<EVVersandkanal, number>
  epost_ordner: string
  fehler: { name: string; kanal: string; status: string; text: string }[]
}

export interface EVVersandprotokoll {
  id: string
  person: string
  person_name: string
  kanal: EVVersandkanal
  kanal_display: string
  status: 'erfolgreich' | 'fehlgeschlagen' | 'uebersprungen'
  empfaenger: string
  epost_pfad: string
  fehlertext: string
  versendet_am: string
  versendet_von: number | null
  versendet_von_name: string | null
}

export interface EVEreignis {
  id: string
  typ: string
  typ_display: string
  top: string | null
  text: string
  alter_wert: string
  neuer_wert: string
  erstellt_am: string
  erstellt_von: number | null
  erstellt_von_name: string | null
}

export interface EVEinladungPdfErgebnis {
  dokument_id: string
  dateiname: string
  download_url: string
}

// --- Phase D: Durchführung und Beschlussfassung ---

export interface EVQuorum {
  gesamt_stimmkraft: string
  anwesende_stimmkraft: string
  anwesend_prozent: string
  anzahl_teilnehmer: number
  anzahl_anwesend: number
  anzahl_anwesenheit_offen: number
  hinweis: string
}

export type EVVotum = 'ja' | 'nein' | 'enthaltung'

export interface EVStimme {
  id: string
  top: string
  teilnehmer: string
  person_name: string
  votum: EVVotum
  votum_display: string
  stimmkraft: string
  erfasst_am: string
  erfasst_von: number | null
}

export type EVAnfechtungStatus = 'keine' | 'anhaengig' | 'abgewiesen' | 'aufgehoben'

export interface EVBeschluss {
  id: string
  objekt: string
  objekt_bezeichnung: string
  nummer: number
  ev: string | null
  top: string | null
  top_nummer: number | null
  top_titel: string | null
  beschluss_datum: string
  ort: string
  wortlaut: string
  ergebnis_ja: string
  ergebnis_nein: string
  ergebnis_enthaltung: string
  dokument: string | null
  dokument_dateiname: string | null
  vorgang: string | null
  vorgang_nummer: string | null
  anfechtung_status: EVAnfechtungStatus
  anfechtung_status_display: string
  anfechtung_notiz: string
  aufgehoben_am: string | null
  gerichtlicher_hinweis: string
  erstellt_am: string
  erstellt_von: number | null
  erstellt_von_name: string | null
}

export interface EVUebernahmeErgebnis {
  beschluesse: number
  uebersprungen: number
  vorgaenge: number
  mit_vorgang_trigger: number
  mit_wp_trigger: number
  nummern: number[]
  protokoll_dokument_id: string
}

export interface EVAnwesenheitPayload {
  ist_anwesend?: boolean | null
  vertreten_durch?: string | null
  vertreter_name?: string
  vollmacht_dokument?: string | null
  zusage_status?: 'offen' | 'zugesagt' | 'abgesagt'
}
