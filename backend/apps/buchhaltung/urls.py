from rest_framework.routers import DefaultRouter
from .views import (
    BuchungsartViewSet,
    BuchungViewSet,
    BuchungsstapelViewSet,
    OffenerPostenViewSet,
    SollstellungsLaufViewSet, SollstellungViewSet,
    CamtImportEinstellungViewSet, CamtImportLogViewSet,
    ImportOrdnerEinstellungViewSet, KontoumsatzViewSet,
    MahnlaufViewSet, MahnungViewSet, MahnsperreViewSet,
    ForderungsfallViewSet, BasiszinssatzViewSet,
    RAPPositionViewSet, RAPAufloesungViewSet,
    BankImportViewSet,
    JahresabrechnungViewSet, EinzelAbrechnungViewSet,
    LastschriftLaufViewSet,
)

router = DefaultRouter()
router.register(r'buchungsarten', BuchungsartViewSet, basename='buchungsarten')
router.register(r'buchungen', BuchungViewSet, basename='buchungen')
router.register(r'buchungsstapel', BuchungsstapelViewSet, basename='buchungsstapel')
router.register(r'offene-posten', OffenerPostenViewSet, basename='offene-posten')
router.register(r'sollstellungslaeufe', SollstellungsLaufViewSet, basename='sollstellungslaeufe')
router.register(r'sollstellungen', SollstellungViewSet, basename='sollstellungen')
router.register(r'camt-einstellungen', CamtImportEinstellungViewSet, basename='camt-einstellungen')
router.register(r'camt-logs', CamtImportLogViewSet, basename='camt-logs')
router.register(r'import-ordner', ImportOrdnerEinstellungViewSet, basename='import-ordner')
router.register(r'kontoumsaetze', KontoumsatzViewSet, basename='kontoumsaetze')
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

urlpatterns = router.urls
