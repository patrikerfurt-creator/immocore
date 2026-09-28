"""
Lesbare Vorschau einer abgelegten Mail (``.eml``/``.msg``) im Browser.

Browser können das Outlook-Format nicht darstellen und laden ``.msg`` nur
herunter. Diese Vorschau rendert die Mail stattdessen aus der Originaldatei
als HTML — ohne eine zweite Datei anzulegen: Erzeugt wird bei jedem Abruf
neu, das Original im DMS bleibt die einzige gespeicherte Fassung.

SICHERHEIT — der wesentliche Punkt hier:

Eine eingegangene Mail ist FREMDER, nicht vertrauenswürdiger Inhalt. Würde
man ihr HTML einfach durchreichen, führte eine bösartige Mail Skripte im
Kontext der Anwendung aus (XSS) und könnte die Sitzung des Mitarbeiters
übernehmen. Deshalb:

- Ausgegeben wird ausschliesslich der vom Parser extrahierte TEXT, jedes
  Zeichen HTML-escaped. Kein Markup aus der Mail überlebt.
- Der Endpunkt setzt zusätzlich eine Content-Security-Policy, die Skripte,
  externe Bilder und Einbettungen verbietet — zweite Verteidigungslinie,
  falls hier je jemand Markup durchlassen sollte.

Der Preis: Die Vorschau zeigt Text, keine originalgetreue Formatierung.
Bilder, Tabellen und Schriftauszeichnungen der Mail fehlen. Wer das Original
braucht, lädt die Datei herunter — sie liegt unverändert im DMS.
"""
import html

from django.utils import timezone

from apps.vorgaenge.services.mail_import_service import ERLAUBTE_ENDUNGEN, parse_mail

# Erlaubt nichts: keine Skripte, keine externen Bilder, keine Frames. Die
# Vorschau braucht nur Text und Inline-CSS.
CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; "
       "script-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")

_STIL = """
:root { color-scheme: light dark; }
body { font: 14px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif;
       margin: 0; padding: 24px; background: #fff; color: #1f2933; }
.kopf { border: 1px solid #d9e0e7; border-radius: 8px; padding: 14px 16px;
        background: #f7f9fb; margin-bottom: 18px; }
.kopf dl { display: grid; grid-template-columns: max-content 1fr;
           gap: 4px 14px; margin: 0; }
.kopf dt { color: #64727f; font-size: 12px; }
.kopf dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; }
h1 { font-size: 17px; margin: 0 0 14px; overflow-wrap: anywhere; }
.text { white-space: pre-wrap; overflow-wrap: anywhere; }
.anhaenge { margin-top: 20px; padding-top: 14px; border-top: 1px solid #e4e9ee; }
.anhaenge ul { margin: 6px 0 0; padding-left: 20px; }
.hinweis { margin-top: 22px; padding-top: 12px; border-top: 1px solid #e4e9ee;
           color: #64727f; font-size: 12px; }
@media (prefers-color-scheme: dark) {
  body { background: #16191d; color: #e4e7eb; }
  .kopf { background: #1e2227; border-color: #333a42; }
  .kopf dt, .hinweis { color: #9aa5b1; }
  .anhaenge, .hinweis { border-color: #333a42; }
}
"""


def ist_mail_dokument(dokument) -> bool:
    """True, wenn das Dokument eine abgelegte Mail ist (nicht ein Anhang)."""
    name = (dokument.dateiname or '').lower()
    return any(name.endswith(endung) for endung in ERLAUBTE_ENDUNGEN)


def _zeile(bezeichnung: str, wert: str) -> str:
    if not wert:
        return ''
    return f'<dt>{html.escape(bezeichnung)}</dt><dd>{html.escape(wert)}</dd>'


def baue_vorschau(pfad, dateiname: str = '', kompakt: bool = False) -> str:
    """Rendert die Mail unter ``pfad`` als eigenständiges HTML-Dokument.

    Jeder Wert aus der Mail geht durch ``html.escape`` — Betreff und
    Absendername genauso wie der Text. Ein Betreff wie
    ``<img src=x onerror=...>`` erscheint damit als sichtbarer Text, nicht
    als Markup.

    ``kompakt=True`` laesst Betreffzeile und Kopfblock weg — fuer die
    Einbettung in eine Maske, die beides schon ueber der Vorschau anzeigt
    (Posteingang). Freistehend geoeffnet braucht die Seite den Kopf dagegen,
    sonst weiss niemand, von wem die Mail stammt.
    """
    parsed = parse_mail(pfad)

    kopf = ''.join([
        _zeile('Von', f"{parsed.absender_name} <{parsed.absender_email}>".strip()
               if parsed.absender_name else parsed.absender_email),
        _zeile('An', parsed.empfaenger),
        _zeile('Gesendet', f"{timezone.localtime(parsed.gesendet_am):%d.%m.%Y %H:%M}"
               if parsed.gesendet_am else ''),
        _zeile('Datei', dateiname or parsed.dateiname),
    ])

    anhaenge = ''
    if parsed.anhaenge_gesamt:
        eintraege = ''.join(
            f'<li>{html.escape(name)}</li>' for name, _ in parsed.anhaenge)
        nicht_gezeigt = parsed.anhaenge_gesamt - len(parsed.anhaenge)
        rest = (f'<p>{nicht_gezeigt} weitere(r) Anhang/Anhänge '
                f'(Signaturgrafiken o. Ä., nicht ins DMS übernommen).</p>'
                if nicht_gezeigt > 0 else '')
        anhaenge = (f'<div class="anhaenge"><strong>Anhänge '
                    f'({parsed.anhaenge_gesamt})</strong><ul>{eintraege}</ul>{rest}</div>')

    titelzeile = '' if kompakt else (
        f"<h1>{html.escape(parsed.betreff or '(ohne Betreff)')}</h1>"
        f'<div class="kopf"><dl>{kopf}</dl></div>')

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(parsed.betreff or dateiname or 'E-Mail')}</title>
<style>{_STIL}</style></head>
<body>
{titelzeile}
<div class="text">{html.escape(parsed.body or '(kein Text)')}</div>
{anhaenge}
<p class="hinweis">Textvorschau aus der archivierten Originaldatei. Bilder und
Formatierung der Mail werden aus Sicherheitsgründen nicht dargestellt — das
unveränderte Original steht im Dokumentenmanagement zum Download bereit.</p>
</body></html>"""
