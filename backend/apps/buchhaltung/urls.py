from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    BuchungsartViewSet,
    BuchungViewSet,
    BuchungsstapelViewSet,
    OffenerPostenViewSet,
    CamtImportEinstellungViewSet, CamtImportLogViewSet,
    ImportOrdnerEinstellungViewSet, KontoumsatzViewSet,
    EBankingBuchungViewSet, BankMatchRegelViewSet, KreditorOPViewSet,
    MahnlaufViewSet, MahnungViewSet, MahnsperreViewSet,
    ForderungsfallViewSet, BasiszinssatzViewSet,
    RAPPositionViewSet, RAPAufloesungViewSet,
    BankImportViewSet,
    JahresabrechnungViewSet, EinzelAbrechnungViewSet,
    LastschriftLaufViewSet,
    WirtschaftsjahrViewSet,
    HausgeldSollstellungslaufViewSet, HausgeldSollstellungViewSet,
    AutoLaufProtokollViewSet,
    SepaZahlungslaufViewSet,
)
from .views_wkz import (
    WKZVorlageViewSet,
    WKZOPViewSet,
    WKZForecastViewSet,
    KreditorWKZVorlagenViewSet,
)

router = DefaultRouter()
router.register(r'buchungsarten', BuchungsartViewSet, basename='buchungsarten')
router.register(r'buchungen', BuchungViewSet, basename='buchungen')
router.register(r'buchungsstapel', BuchungsstapelViewSet, basename='buchungsstapel')
router.register(r'offene-posten', OffenerPostenViewSet, basename='offene-posten')
router.register(r'camt-einstellungen', CamtImportEinstellungViewSet, basename='camt-einstellungen')
router.register(r'camt-logs', CamtImportLogViewSet, basename='camt-logs')
router.register(r'import-ordner', ImportOrdnerEinstellungViewSet, basename='import-ordner')
router.register(r'kontoumsaetze', KontoumsatzViewSet, basename='kontoumsaetze')
router.register(r'e-banking/bank-buchungen', EBankingBuchungViewSet, basename='e-banking-buchungen')
router.register(r'e-banking/bank-match-regeln', BankMatchRegelViewSet, basename='e-banking-match-regeln')
router.register(r'e-banking/kreditor-ops', KreditorOPViewSet, basename='e-banking-kreditor-ops')
router.register(r'mahnlaeufe', MahnlaufViewSet, basename='mahnlaeufe')
router.register(r'mahnungen', MahnungViewSet, basename='mahnungen')
router.register(r'mahnsperren', MahnsperreViewSet, basename='mahnsperren')
router.register(r'forderungsfaelle', ForderungsfallViewSet, basename='forderungsfaelle')
router.register(r'basiszinssaetze', BasiszinssatzViewSet, basename='basiszinssaetze')
router.register(r'rap-positionen', RAPPositionViewSet, basename='rap-positionen')
router.register(r'rap-aufloesungen', RAPAufloesungViewSet, basename='rap-aufloesungen')
router.register(r'bank-importe', BankImportViewSet, basename='bank-importe')
router.register(r'jahresabrechnungen', JahresabrechnungViewSet, basename='jahresabrechnungen')
router.register(r'einzelabrechnungen', EinzelAbrechnungViewSet, basename='einzelabrechnungen')
router.register(r'lastschrift-laeufe', LastschriftLaufViewSet, basename='lastschrift-laeufe')
router.register(r'wirtschaftsjahre',        WirtschaftsjahrViewSet,            basename='wirtschaftsjahre')
router.register(r'hg-laeufe',               HausgeldSollstellungslaufViewSet,  basename='hg-laeufe')
router.register(r'hg-sollstellungen',       HausgeldSollstellungViewSet,       basename='hg-sollstellungen')
router.register(r'auto-lauf-protokolle',    AutoLaufProtokollViewSet,           basename='auto-lauf-protokolle')
router.register(r'sepa-zahlungslaeufe',     SepaZahlungslaufViewSet,            basename='sepa-zahlungslaeufe')

# WKZ-Vorlagen (flache Endpunkte)
router.register(r'wkz-vorlagen', WKZVorlageViewSet, basename='wkz-vorlagen')
router.register(r'wkz-ops', WKZOPViewSet, basename='wkz-ops')

urlpatterns = router.urls + [
    # Nested: /objekte/{objekt_pk}/wkz-vorlagen/ und /objekte/{objekt_pk}/wkz-forecast/
    path(
        'objekte/<str:objekt_pk>/wkz-vorlagen/',
        WKZVorlageViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='objekt-wkz-vorlagen',
    ),
    path(
        'objekte/<str:objekt_pk>/wkz-forecast/',
        WKZForecastViewSet.as_view({'get': 'list'}),
        name='objekt-wkz-forecast',
    ),
    # /kreditoren/{kreditor_pk}/wkz-vorlagen/
    path(
        'kreditoren/<str:kreditor_pk>/wkz-vorlagen/',
        KreditorWKZVorlagenViewSet.as_view({'get': 'list'}),
        name='kreditor-wkz-vorlagen',
    ),
]
