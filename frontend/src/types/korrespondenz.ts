// Typen des Moduls Vorlagen & Korrespondenz (Spec v1.2, Abschnitte 3, 6 und 8).
// Wird über types/index.ts re-exportiert. Phase 5c (Schreiben, Postausgang,
// Druckstapel, Serienlauf) erweitert diese Datei nur.

export type VorlagenAnlass =
  | 'eigentuemer_begruessung'
  | 'eigentuemer_verabschiedung'
  | 'mahnung_stufe_1'
  | 'mahnung_stufe_2'
  | 'mahnung_stufe_3'
  | 'etv_einladung'
  | 'eigentuemer_allgemein'
  | 'vorgang_antwort'

export type VorlagenKanal = 'brief' | 'email' | 'beides'

export type VorlagenVersionStatus = 'entwurf' | 'freigegeben' | 'abgeloest'

// ---- Eingabefelder (Spec 3.5) ----------------------------------------------

export type EingabefeldTyp =
  | 'text' | 'mehrzeilig' | 'datum' | 'uhrzeit' | 'betrag' | 'liste' | 'ja_nein'

export interface Eingabefeld {
  name: string
  label: string
  typ: EingabefeldTyp
  pflicht: boolean
}

// ---- Blockstruktur (Spec 3.4) ----------------------------------------------

export type VorlagenBlockTyp =
  | 'text' | 'baustein' | 'tabelle' | 'liste' | 'bedingt' | 'seitenumbruch' | 'anlage_seite'

export interface TextBlock { typ: 'text'; inhalt: string }
export interface BausteinBlock { typ: 'baustein'; code: string }
// `spalten` ist optional; ohne Angabe nutzt das Backend die Standard-Spalten
// der Quelle. Der Editor reicht das Feld unverändert durch.
export interface TabelleBlock {
  typ: 'tabelle'
  quelle: string
  spalten?: Array<{ feld: string; titel: string; format?: string }>
}
export interface ListeBlock { typ: 'liste'; quelle: string }
export interface BedingtBlock { typ: 'bedingt'; bedingung: string; inhalt: string }
export interface SeitenumbruchBlock { typ: 'seitenumbruch' }
export interface AnlageSeiteBlock { typ: 'anlage_seite'; titel: string; inhalt: string }

export type VorlagenBlock =
  | TextBlock | BausteinBlock | TabelleBlock | ListeBlock
  | BedingtBlock | SeitenumbruchBlock | AnlageSeiteBlock

// ---- Vorlage / Version ------------------------------------------------------

export interface Vorlage {
  id: string
  code: string
  bezeichnung: string
  anlass: VorlagenAnlass
  objekt: string | null
  objekt_bezeichnung?: string | null
  briefbogen: string | null
  kanal_standard: VorlagenKanal
  einzeln_bearbeitbar: boolean
  aktive_version: string | null
  aktive_version_info?: { id: string; version: number; status: VorlagenVersionStatus } | null
  anlass_anzeige?: string
  aktiv: boolean
  erstellt_am?: string
  geaendert_am?: string
}

export type VorlageCreatePayload = Pick<Vorlage, 'code' | 'bezeichnung' | 'anlass'> &
  Partial<Pick<Vorlage, 'objekt' | 'briefbogen' | 'kanal_standard' | 'einzeln_bearbeitbar' | 'aktiv'>>

// Code, Anlass und Objekt sind nach dem Anlegen fest (Backend: VorlageAendernSerializer).
export type VorlageUpdatePayload = Partial<
  Pick<Vorlage, 'bezeichnung' | 'briefbogen' | 'kanal_standard' | 'einzeln_bearbeitbar' | 'aktiv'>
>

export interface VorlagenVersion {
  id: string
  vorlage: string
  version: number
  betreff: string
  inhalt: VorlagenBlock[]
  email_begleittext: string
  eingabefelder: Eingabefeld[]
  pflicht_platzhalter: string[]
  parameter: Record<string, unknown>
  status: VorlagenVersionStatus
  status_anzeige?: string
  freigegeben_am: string | null
  freigegeben_von?: number | string | null
  freigegeben_von_name?: string | null
  erstellt_am?: string
}

export type VorlagenVersionPayload = Partial<
  Pick<VorlagenVersion,
    'betreff' | 'inhalt' | 'email_begleittext' | 'eingabefelder' | 'pflicht_platzhalter' | 'parameter'>
> & {
  /** Nur beim Anlegen: kopiert diese Version als Ausgangspunkt. */
  basis_version?: string
}

export interface VorlagenVersionVorschauPayload {
  person_id: string
  einheit_id?: string | null
  eingabewerte?: Record<string, unknown>
}

// ---- Platzhalter (Spec 4.3) -------------------------------------------------

export type PlatzhalterTyp = 'text' | 'zahl' | 'betrag' | 'datum' | 'bool' | 'liste' | 'tabelle'

export interface Platzhalter {
  /** Voller Name inkl. Gruppe, so wie im Text verwendet: `empfaenger.briefanrede`. */
  name: string
  beschreibung: string
  typ: PlatzhalterTyp | string
  beispiel: string | number | boolean | null
  gruppe: string
}

// ---- Textbaustein / Briefbogen (Spec 3.1, 3.6) ------------------------------

export interface Textbaustein {
  id: string
  code: string
  bezeichnung: string
  inhalt: string
  objekt: string | null
  aktiv: boolean
}

export type TextbausteinPayload = Partial<Omit<Textbaustein, 'id'>>

export interface Briefbogen {
  id: string
  bezeichnung: string
  firma_name: string
  firma_strasse: string
  firma_plz: string
  firma_ort: string
  telefon: string
  email: string
  web: string
  sprechzeiten: string
  hinweis_infoblock: string
  logo: string | null
  fuss_logo: string | null
  fuss_firma_zeile1: string
  fuss_firma_zeile2: string
  fuss_firma_zeile3: string
  pflichtangaben: string
  pflichtangaben_anzeigen: boolean
  steuerzeichen_unsichtbar: string
  ist_standard: boolean
  aktiv: boolean
}

export type BriefbogenPayload = Partial<Omit<Briefbogen, 'id'>>

// ---- KI-Assistent (Spec 6) --------------------------------------------------

export interface VorlagenAssistentAnfrage {
  anlass: VorlagenAnlass | string
  stichworte: string
  /** Nur bei „Mit KI überarbeiten": der zu überarbeitende Block. */
  block?: VorlagenBlock
  /** Im Editor definierte Eingabefelder (Name/Label/Typ, keine Werte) — macht `eingabe.*` für die KI bekannt. */
  eingabefelder?: Eingabefeld[]
}

export interface VorlagenAssistentResponse {
  bloecke: VorlagenBlock[]
  hinweise: string[]
  /** Vorschlag für den Betreff (kann leer sein). */
  betreff?: string
}

// ---- Schreiben / Postausgang (Spec 3.8, 3.10, 7.1-7.3, 8) --------------------

export type SchreibenStatus =
  | 'entwurf' | 'zur_pruefung' | 'freigegeben' | 'versendet' | 'versand_fehlgeschlagen' | 'verworfen'

/** Kanal beim Erstellen/Versenden: `beides` = E-Mail und Brief. */
export type SchreibenKanal = 'brief' | 'email' | 'beides'

export interface SchreibenVorlageRef {
  id: string
  code: string
  bezeichnung: string
  anlass: VorlagenAnlass
}

/** Listenformat (`GET /schreiben/`); `fehler` gefüllt + Status `entwurf` = „nicht erzeugbar“. */
export interface Schreiben {
  id: string
  nummer: string
  status: SchreibenStatus
  status_anzeige: string
  nicht_erzeugbar: boolean
  fehler: string
  kanal: string
  auch_brief: boolean
  betreff: string
  vorlage: SchreibenVorlageRef
  einzeln_bearbeitbar: boolean
  empfaenger: { id: string; name: string } | null
  objekt: { id: string; bezeichnung: string } | null
  einheit: { id: string; einheit_nr: string } | null
  serienlauf: string | null
  vorgang: string | null
  /** Einzel-PDF im DMS (erst nach der Freigabe). */
  dokument: string | null
  druckstapel: string | null
  erstellt_am: string
  freigegeben_am: string | null
  versendet_am: string | null
}

export interface SchreibenDetail extends Schreiben {
  html_gerendert: string
  /** Vom Mitarbeiter angepasster Inhalt (Blockliste); `null` = Originalinhalt der Vorlage. */
  inhalt_angepasst: VorlagenBlock[] | null
  eingabewerte: Record<string, unknown>
  ihr_zeichen: string
  ihr_schreiben_vom: string | null
  unterzeichner: number | null
  mail_message_id: string
  freigegeben_von: number | null
}

export interface SchreibenVersandAntwort extends SchreibenDetail {
  versand: { ergebnis: 'versendet' | 'druckstapel' | 'fehlgeschlagen'; hinweis: string }
}

export interface SchreibenCreatePayload {
  vorlage_code: string
  empfaenger: string
  objekt?: string | null
  einheit?: string | null
  eigentumsverhaeltnis?: string | null
  vorgang?: string | null
  eingabewerte?: Record<string, unknown>
  kanal?: SchreibenKanal | null
  /** User-Id; ohne Angabe = der erstellende Mitarbeiter. */
  unterzeichner?: number | null
  ihr_zeichen?: string
  ihr_schreiben_vom?: string | null
}

/** Filter der Postausgangs-Liste. `status`: leer = Postausgang, sonst kommagetrennt bzw. `nicht_erzeugbar`/`alle`. */
export interface SchreibenListeParams {
  status?: string
  objekt?: string
  anlass?: string
  betreuer?: string
  serienlauf?: string
  druckbereit?: string
}

// ---- Druckstapel (Spec 7.3) -------------------------------------------------

export type DruckstapelStatus = 'offen' | 'bestaetigt'

export interface Druckstapel {
  id: string
  status: DruckstapelStatus
  status_anzeige: string
  /** Dokument-Id des Sammel-PDFs (`GET /dokumente/{id}/datei/`). */
  dokument: string | null
  anzahl: number
  schreiben: Array<{ id: string; nummer: string; status: SchreibenStatus }>
  erstellt_am: string
  erstellt_von: number | null
  bestaetigt_am: string | null
  bestaetigt_von: number | null
}

export interface DruckstapelCreatePayload {
  schreiben_ids?: string[]
  objekt?: string | null
}

// ---- Serienlauf (Spec 3.9, 7.4) ---------------------------------------------

export type SerienlaufStatus = 'vorschau' | 'zur_pruefung' | 'freigegeben' | 'versendet' | 'teilweise_fehler'

export interface SerienlaufFilter {
  einheit_typ?: string[]
  email_zustimmung?: '' | 'mit' | 'ohne'
  /** Eigentumsverhältnis-Ids (manuelle Abwahl). */
  ausschliessen?: string[]
  /** Eigentumsverhältnis-Ids (manuelle Zuwahl). */
  hinzufuegen?: string[]
}

export interface SerienlaufCreatePayload {
  vorlage_version?: string
  vorlage_code?: string
  objekt: string
  empfaenger_filter?: SerienlaufFilter
  eingabewerte?: Record<string, unknown>
  unterzeichner?: number | null
}

export interface SerienlaufVorschauEintrag {
  schreiben_id: string
  nummer: string
  empfaenger: string
  einheit_nr: string
  betreff: string
  html_gerendert: string
}

export interface SerienlaufNichtErzeugbar {
  schreiben_id: string
  nummer: string
  empfaenger: string
  einheit_nr: string
  ursache: string
}

export interface Serienlauf {
  id: string
  status: SerienlaufStatus
  status_anzeige: string
  vorlage_version: string
  vorlage: SchreibenVorlageRef
  objekt: { id: string; bezeichnung: string } | null
  empfaenger_filter: SerienlaufFilter
  eingabewerte: Record<string, unknown>
  unterzeichner: number | null
  anzahl: number
  zaehler: { gesamt: number; nicht_erzeugbar: number; je_status: Record<string, number> }
  vorschau: { erzeugbar_anzahl: number; zufaellig: SerienlaufVorschauEintrag[] }
  nicht_erzeugbar: SerienlaufNichtErzeugbar[]
  freigebbar: boolean
  /** Gründe, warum der Lauf (noch) nicht freigegeben werden kann. */
  blocker: string[]
  /** Dokument-Id des Sammel-PDFs aller Briefe (nach der Verarbeitung). */
  druck_dokument: string | null
  druckstapel_ids: string[]
  erstellt_am: string
  freigegeben_am: string | null
}
