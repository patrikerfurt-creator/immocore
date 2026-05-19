# Pflicht-Filter für zukünftiges Mahnwesen

Sobald das Mahnwesen-Modul implementiert wird, MUSS die Selektion
der zu mahnenden Sollstellungen folgende zwei Filter setzen:

```python
mahnbare = HausgeldSollstellung.objects.filter(
    soll_betrag__gt=models.F('ist_betrag'),
    neutralisiert_durch_opos__isnull=True,
).exclude(
    sollstellungs_typ='korrektur',
)
```

Begründung:
- `neutralisiert_durch_opos__isnull=True`: Originale, die durch eine
  Korrektur (Eigentümerwechsel, Wirtschaftsplan-Änderung) neutralisiert
  wurden, dürfen nicht gemahnt werden.
- `sollstellungs_typ != 'korrektur'`: Korrektur-Sollstellungen selbst
  (mit negativem Betrag) dürfen nicht gemahnt werden — sie sind keine
  Forderungen gegen den Eigentümer, sondern Verbindlichkeiten.

Quellen:
- IMMOCORE_ClaudeCode_KorrekturService_v1_2.md Kap. 6
- IMMOCORE_ClaudeCode_RueckwirkenderEigentuemerwechsel_v1_1.md Kap. 9
