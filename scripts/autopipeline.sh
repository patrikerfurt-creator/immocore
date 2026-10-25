#!/usr/bin/env bash
#
# autopipeline.sh — Eingabemaske für die Autopipeline (Backfill).
#
# Zweck: Vergangene Monate im Live-Betrieb nachfahren. Fragt Objektnummer,
# Von- und Bis-Monat ab und ruft je Monat das Management-Kommando
# `autopipeline_lauf` im Backend-Container auf. Das erzeugt pro Monat:
#   1. Hausgeld-Sollstellung
#   2. SEPA-Lastschriften (pain.008)
#   3. WKZ-OPs (wiederkehrende Buchungen)
#
# Alle Schritte sind idempotent: bereits committete Monate werden übersprungen.
#
# Verwendung (im Verzeichnis mit der docker-compose-Datei ausführen):
#   # Produktion (Default):
#   ./scripts/autopipeline.sh
#
#   # Test/Dev:
#   COMPOSE_FILE=docker-compose.yml ./scripts/autopipeline.sh
#
# Konfiguration über Umgebungsvariablen (mit Defaults):
#   COMPOSE_FILE (docker-compose.prod.yml) · BACKEND_SERVICE (backend)
#
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKEND_SERVICE="${BACKEND_SERVICE:-backend}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "FEHLER: Compose-Datei '$COMPOSE_FILE' nicht gefunden (Arbeitsverzeichnis: $(pwd))." >&2
    exit 1
fi

run_manage() {
    # Stdin auf /dev/null: sonst zieht `docker compose exec` die restlichen
    # Eingabezeilen (z.B. die ja/nein-Bestätigung) aus der Pipe ein.
    docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" python manage.py "$@" < /dev/null
}

# Monats-Arithmetik ohne date-Abhängigkeit: YYYYMM als Ganzzahl.
ym_to_int()   { echo $(( $1 * 12 + ($2 - 1) )); }       # (jahr, monat) -> laufende Monatszahl
int_to_year() { echo $(( $1 / 12 )); }
int_to_mon()  { printf '%02d' $(( $1 % 12 + 1 )); }

echo "============================================================"
echo "  IMMOCORE — Autopipeline (Backfill)"
echo "  Stack: $COMPOSE_FILE"
echo "============================================================"
echo "  Pro Monat werden erzeugt: Sollstellung + Lastschriften + WKZ"
echo "  Bereits gebuchte Monate werden automatisch übersprungen."
echo "------------------------------------------------------------"

# --- Objektnummer ----------------------------------------------------------
read -r -p "Objektnummer: " OBJEKT
OBJEKT="${OBJEKT// /}"
if [[ -z "$OBJEKT" ]]; then
    echo "FEHLER: Keine Objektnummer eingegeben." >&2
    exit 1
fi

# --- Von-Monat -------------------------------------------------------------
read -r -p "Von-Monat (JJJJ-MM): " VON
if [[ ! "$VON" =~ ^([0-9]{4})-(0[1-9]|1[0-2])$ ]]; then
    echo "FEHLER: Ungültiges Monatsformat '$VON' — erwartet JJJJ-MM (z.B. 2025-01)." >&2
    exit 1
fi
VON_JAHR="${BASH_REMATCH[1]}"; VON_MON="${BASH_REMATCH[2]}"

# --- Bis-Monat (Default = Von) ---------------------------------------------
read -r -p "Bis-Monat (JJJJ-MM) [Default $VON]: " BIS
BIS="${BIS:-$VON}"
if [[ ! "$BIS" =~ ^([0-9]{4})-(0[1-9]|1[0-2])$ ]]; then
    echo "FEHLER: Ungültiges Monatsformat '$BIS' — erwartet JJJJ-MM." >&2
    exit 1
fi
BIS_JAHR="${BASH_REMATCH[1]}"; BIS_MON="${BASH_REMATCH[2]}"

VON_INT=$(ym_to_int "$VON_JAHR" "$((10#$VON_MON))")
BIS_INT=$(ym_to_int "$BIS_JAHR" "$((10#$BIS_MON))")
if (( BIS_INT < VON_INT )); then
    echo "FEHLER: Bis-Monat ($BIS) liegt vor Von-Monat ($VON)." >&2
    exit 1
fi

# --- Monatsliste aufbauen --------------------------------------------------
MONATE=()
for (( i = VON_INT; i <= BIS_INT; i++ )); do
    MONATE+=( "$(int_to_year "$i")-$(int_to_mon "$i")" )
done

echo "------------------------------------------------------------"
echo "  Objekt : $OBJEKT"
echo "  Monate : ${MONATE[*]}  (${#MONATE[@]} Monat/e)"
echo "------------------------------------------------------------"

# --- Validierung per Dry-Run (erster Monat) --------------------------------
echo "Prüfe Objekt (Dry-Run, keine Buchungen)…"
echo
run_manage autopipeline_lauf --monat "${MONATE[0]}" --objekt "$OBJEKT" --dry-run
echo

# --- Bestätigung -----------------------------------------------------------
read -r -p "Jetzt ECHT buchen (Sollstellung + Lastschrift + WKZ)? Tippe 'ja': " ANTWORT
if [[ "$ANTWORT" != "ja" ]]; then
    echo "Abgebrochen — nichts gebucht."
    exit 0
fi

# --- Echter Lauf, Monat für Monat ------------------------------------------
FEHLGESCHLAGEN=()
for M in "${MONATE[@]}"; do
    echo
    echo "############################################################"
    echo "#  $OBJEKT — $M"
    echo "############################################################"
    if run_manage autopipeline_lauf --monat "$M" --objekt "$OBJEKT"; then
        :
    else
        echo "!! Monat $M mit Fehler beendet." >&2
        FEHLGESCHLAGEN+=( "$M" )
    fi
done

echo
echo "============================================================"
if (( ${#FEHLGESCHLAGEN[@]} == 0 )); then
    echo "  ✅ Fertig — alle ${#MONATE[@]} Monat/e verarbeitet."
else
    echo "  ⚠️  Fertig mit Fehlern in: ${FEHLGESCHLAGEN[*]}"
fi
echo "============================================================"
