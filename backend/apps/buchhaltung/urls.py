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
)
from .views_verteiler import (
    aktive_vs_view, export_view,
    import_preview_view, import_commit_view,
    protokoll_view,
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

_VS_PREFIX = 'objekte/<uuid:objekt_id>/verteiler/'

urlpatterns = router.urls + [
    path(_VS_PREFIX + 'aktive-vs/',         aktive_vs_view,        name='verteiler-aktive-vs'),
    path(_VS_PREFIX + 'export/',            export_view,           name='verteiler-export'),
    path(_VS_PREFIX + 'import/preview/',    import_preview_view,   name='verteiler-import-preview'),
    path(_VS_PREFIX + 'import/commit/',     import_commit_view,    name='verteiler-import-commit'),
    path(_VS_PREFIX + 'protokoll/',         protokoll_view,        name='verteiler-protokoll'),
]
