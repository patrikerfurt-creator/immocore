ABFRAGE_KATALOG = [
    {
        "id": "personenkonten_rueckstaende",
        "beschreibung": (
            "Zeigt alle Eigentuemer im Objekt mit offenen oder "
            "teilbezahlten Hausgeld-Sollstellungen (Rueckstaenden). "
            "Gibt Namen, Einheit, OPOS-Betrag und Rueckstandssumme zurueck."
        ),
        "endpunkt": "/api/v1/sollstellungen/",
        "methode": "GET",
        "pflicht_parameter": ["objekt_nr"],
        "optionale_parameter": ["status", "min_rueckstand"],
        "parameter_schema": {
            "objekt_nr": "integer — 6-stellige Objektnummer",
            "status": "string — 'offen' | 'teilbezahlt' | 'ausgeglichen' | 'storniert' (default: 'offen,teilbezahlt')",
            "min_rueckstand": "decimal — Mindest-Rueckstandsbetrag in EUR (optional)",
        },
        "ergebnis_spalten": ["eigentuemer", "einheit_nr", "periode", "soll_betrag", "ist_betrag", "rueckstand"],
    },
    {
        "id": "einheiten_ohne_eigentuemer",
        "beschreibung": (
            "Zeigt alle Einheiten eines Objekts, die aktuell kein aktives "
            "EigentumsVerhaeltnis (kein Vertrag) haben."
        ),
        "endpunkt": "/api/v1/einheiten/",
        "methode": "GET",
        "pflicht_parameter": ["objekt_nr"],
        "optionale_parameter": ["einheit_typ"],
        "parameter_schema": {
            "objekt_nr": "integer — 6-stellige Objektnummer",
            "einheit_typ": "string — 'Wohnung' | 'Gewerbe' | 'Stellplatz' | 'Sonstiges' (optional)",
            "ohne_eigentuemer": "string — immer '1' setzen fuer diesen Katalog-Eintrag",
        },
        "feste_parameter": {"ohne_eigentuemer": "1"},
        "filter_hinweis": "Nur Einheiten ohne aktives EigentumsVerhaeltnis (ende__isnull=True).",
        "ergebnis_spalten": ["einheit_nr", "einheit_typ", "lage", "flaeche_qm", "letzter_eigentuemer"],
    },
    {
        "id": "offene_rechnungen",
        "beschreibung": (
            "Zeigt alle Rechnungen eines Objekts in einem bestimmten Status "
            "(z.B. in_pruefung, freigegeben). Optional filterbar nach "
            "Mindestbetrag oder Zeitraum."
        ),
        "endpunkt": "/api/v1/rechnungen/",
        "methode": "GET",
        "pflicht_parameter": ["objekt_nr"],
        "optionale_parameter": ["status", "min_betrag", "von_datum", "bis_datum"],
        "parameter_schema": {
            "objekt_nr": "integer",
            "status": "string — 'in_buchhaltung' | 'zur_freigabe' | 'freigegeben' | 'teilbezahlt' | 'bezahlt' | 'abgelehnt' | 'storniert' (default: 'in_pruefung,freigegeben')",
            "min_betrag": "decimal",
            "von_datum": "date — ISO 8601 (YYYY-MM-DD)",
            "bis_datum": "date — ISO 8601 (YYYY-MM-DD)",
        },
        "ergebnis_spalten": ["rechnungsnummer", "kreditor", "betrag_brutto", "status", "faelligkeit", "zugewiesen_an"],
    },
    {
        "id": "objekte_liste",
        "beschreibung": (
            "Zeigt alle aktiven Objekte des Mandanten mit Basisdaten. "
            "Nuetzlich wenn der Nutzer ein Objekt sucht oder eine Uebersicht moechte."
        ),
        "endpunkt": "/api/v1/objekte/",
        "methode": "GET",
        "pflicht_parameter": [],
        "optionale_parameter": ["objekt_typ", "status"],
        "parameter_schema": {
            "objekt_typ": "string — 'WEG' | 'ZH' | 'SEV' (optional)",
            "status": "string — 'aktiv' | 'archiviert' (default: 'aktiv')",
        },
        "ergebnis_spalten": ["objekt_nr", "bezeichnung", "ort", "objekt_typ", "anzahl_wohnungen", "anzahl_stellplaetze"],
        "summen_spalten": ["anzahl_wohnungen", "anzahl_stellplaetze"],
    },
    {
        "id": "einheiten_eines_objekts",
        "beschreibung": (
            "Zeigt alle Einheiten eines Objekts mit aktuellem Eigentuemer "
            "und Hausgeld-Soll."
        ),
        "endpunkt": "/api/v1/einheiten/",
        "methode": "GET",
        "pflicht_parameter": ["objekt_nr"],
        "optionale_parameter": ["einheit_typ"],
        "parameter_schema": {
            "objekt_nr": "integer",
            "einheit_typ": "string — optional",
        },
        "ergebnis_spalten": ["einheit_nr", "einheit_typ", "lage", "aktueller_eigentuemer", "hausgeld_soll"],
    },
    {
        "id": "offene_sollstellungen_eigentuemer",
        "beschreibung": (
            "Zeigt alle offenen Hausgeld-Sollstellungen eines bestimmten "
            "Eigentuemers (Name oder IBAN), optional auf ein Objekt eingeschraenkt."
        ),
        "endpunkt": "/api/v1/sollstellungen/",
        "methode": "GET",
        "pflicht_parameter": ["person_name_oder_iban"],
        "optionale_parameter": ["objekt_nr", "status"],
        "parameter_schema": {
            "person_name_oder_iban": "string — Freitextsuche ueber Vor-/Nachname oder IBAN",
            "objekt_nr": "integer — optional",
            "status": "string — default: 'offen,teilbezahlt'",
        },
        "ergebnis_spalten": ["objekt", "einheit_nr", "periode", "soll_betrag", "ist_betrag", "rueckstand"],
    },
    {
        "id": "tickets_offen",
        "beschreibung": (
            "Zeigt alle offenen Tickets (Aufgaben, Maengelmeldungen) eines Objekts, "
            "optional nach Ticket-Typ oder zugewiesenem Bearbeiter filterbar."
        ),
        "endpunkt": "/api/v1/tickets/",
        "methode": "GET",
        "pflicht_parameter": ["objekt_nr"],
        "optionale_parameter": ["ticket_typ", "zuweisung", "status"],
        "parameter_schema": {
            "objekt_nr": "integer",
            "ticket_typ": "string — optional",
            "zuweisung": "string — Username des Bearbeiters (optional)",
            "status": "string — default: 'offen'",
        },
        "ergebnis_spalten": ["ticket_nr", "titel", "ticket_typ", "status", "zuweisung", "erstellt_am"],
    },
    {
        "id": "bankkonten_eines_objekts",
        "beschreibung": (
            "Zeigt alle Bankkonten (Bewirtschaftung + Ruecklagen) eines Objekts "
            "mit IBAN und Kontobezeichnung."
        ),
        "endpunkt": "/api/v1/objekte/{objekt_nr}/bankkonten/",
        "methode": "GET",
        "pflicht_parameter": ["objekt_nr"],
        "optionale_parameter": [],
        "parameter_schema": {
            "objekt_nr": "integer",
        },
        "ergebnis_spalten": ["bezeichnung", "konto_typ", "iban", "aktiv"],
    },
]
