STAMM_VS_DIREKT = {"001", "010"}
STAMM_VS_KOPF   = {"030", "031", "032"}
VERBRAUCHS_VS_CODES = {"140", "141", "142", "143", "144", "145"}
ALL_KNOWN_VS = STAMM_VS_DIREKT | STAMM_VS_KOPF | VERBRAUCHS_VS_CODES

STAMM_VS_MAASSEINHEIT = {
    "001": "m²",
    "010": "Tausendstel",
    "030": "Anzahl",
    "031": "Anzahl",
    "032": "Anzahl",
}

EINHEIT_TYP_REIHENFOLGE = {
    "Wohnung":    0,
    "Gewerbe":    1,
    "Stellplatz": 2,
    "Sonstiges":  3,
}

# Excel number format codes (internal US-style, displayed per locale)
ZELL_FORMAT = {
    "001": '#,##0.00',
    "010": '#,##0',
    "030": '0',
    "031": '0',
    "032": '0',
    "140": '#,##0.0000',
    "141": '#,##0.0000',
    "142": '#,##0.0000',
    "143": '#,##0.0000',
    "144": '#,##0.0000',
    "145": '#,##0.0000',
}
