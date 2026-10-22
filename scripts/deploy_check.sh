#!/usr/bin/env bash
#
# deploy_check.sh — Vorher/Nachher-Zeilenzählung aller DB-Tabellen für Deploys.
#
# Zweck: Vor einem Deploy einen Snapshot der Zeilenzahlen ziehen, nach dem
# Deploy erneut zählen und vergleichen. So fällt sofort auf, falls ein Deploy
# (z. B. durch Migrationen oder Importe) Datensätze verändert oder verliert.
#
# Verwendung (im Verzeichnis mit der docker-compose-Datei ausführen):
#   # Produktion:
#   COMPOSE_FILE=docker-compose.prod.yml ./scripts/deploy_check.sh before
#   ... Deploy durchführen ...
#   COMPOSE_FILE=docker-compose.prod.yml ./scripts/deploy_check.sh after
#
#   # Test/Dev (Default-Compose):
#   ./scripts/deploy_check.sh before   &&  ...  &&  ./scripts/deploy_check.sh after
#
# Konfiguration über Umgebungsvariablen (mit Defaults):
#   COMPOSE_FILE (docker-compose.yml) · DB_SERVICE (db) · DB_USER (immocore)
#   DB_NAME (immocore) · SNAPSHOT (/tmp/deploy_counts_before.tsv)
#
# Exit-Codes: 0 = alles identisch · 1 = Abweichung gefunden · 2 = Bedienfehler
#
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${DB_USER:-immocore}"
DB_NAME="${DB_NAME:-immocore}"
SNAPSHOT="${SNAPSHOT:-/tmp/deploy_counts_before.tsv}"

# Exakte Zeilenzahl je Tabelle im Schema 'public' (eine Query, via query_to_xml),
# sortiert nach Tabellenname für den späteren Vergleich.
zaehle() {
  docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    psql -U "$DB_USER" -d "$DB_NAME" -tA -F$'\t' -c \
    "SELECT relname,
            (xpath('/row/c/text()',
                   query_to_xml(format('select count(*) c from %I.%I', schemaname, relname),
                                false, true, '')))[1]::text::bigint
     FROM pg_stat_user_tables
     ORDER BY relname;" \
  | sort -t$'\t' -k1,1
}

cmd="${1:-}"
case "$cmd" in
  before)
    zaehle > "$SNAPSHOT"
    echo "Vorher-Snapshot gespeichert: $SNAPSHOT ($(wc -l < "$SNAPSHOT") Tabellen, $(awk -F'\t' '{s+=$2} END{print s}' "$SNAPSHOT") Zeilen gesamt)"
    ;;
  after|compare)
    if [ ! -f "$SNAPSHOT" ]; then
      echo "FEHLER: Kein Vorher-Snapshot gefunden ($SNAPSHOT). Erst '$0 before' ausführen." >&2
      exit 2
    fi
    nachher="$(mktemp)"
    trap 'rm -f "$nachher"' EXIT
    zaehle > "$nachher"

    echo "Vergleich vorher → nachher  (Snapshot: $SNAPSHOT)"
    printf '%-40s %12s %12s   %s\n' "Tabelle" "vorher" "nachher" "Status"
    printf '%s\n' "----------------------------------------------------------------------------------"
    # -a1 -a2: auch Tabellen anzeigen, die nur auf einer Seite existieren.
    join -t$'\t' -a1 -a2 -e FEHLT -o '0,1.2,2.2' "$SNAPSHOT" "$nachher" \
      | awk -F'\t' '
          { status = ($2==$3 ? "OK" : "<<< ABWEICHUNG"); if ($2!=$3) abw++ ;
            printf "%-40s %12s %12s   %s\n", $1, $2, $3, status }
          END { exit (abw>0 ? 1 : 0) }'
    rc=$?
    echo "----------------------------------------------------------------------------------"
    if [ "$rc" -ne 0 ]; then
      echo "WARNUNG: Abweichungen gefunden — bitte prüfen!" >&2
      exit 1
    fi
    echo "Alle Tabellen identisch — kein Datenverlust."
    ;;
  *)
    echo "Usage: $0 before|after" >&2
    echo "Env: COMPOSE_FILE DB_SERVICE DB_USER DB_NAME SNAPSHOT" >&2
    exit 2
    ;;
esac
