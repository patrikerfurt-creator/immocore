from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    GewerkAdminViewSet,
    GewerkViewSet,
    HandwerkerauftragViewSet,
    ObjektHandwerkerViewSet,
)
from .views_oeffentlich import OeffentlicherAuftragBestaetigenView, OeffentlicherAuftragDetailView

router = DefaultRouter()
# Reihenfolge wichtig: 'gewerke/admin' muss VOR 'gewerke' registriert werden,
# damit die Admin-Detail-Route (…/admin/<pk>/) nicht von der generischen
# 'gewerke/<pk>/'-Route des Lese-ViewSets verschluckt wird (Muster:
# apps.vorgaenge.urls / vorgang-typen).
router.register(r'gewerke/admin', GewerkAdminViewSet, basename='gewerke-admin')
router.register(r'gewerke', GewerkViewSet, basename='gewerke')
router.register(r'handwerkerauftraege', HandwerkerauftragViewSet, basename='handwerkerauftraege')
router.register(r'objekt-handwerker', ObjektHandwerkerViewSet, basename='objekt-handwerker')

urlpatterns = router.urls + [
    # Öffentliche Routen klar getrennt unter 'oeffentlich/' (Orchestrator-Vorgabe).
    path(
        'oeffentlich/auftrag/<str:token>/',
        OeffentlicherAuftragDetailView.as_view(),
        name='oeffentlich-auftrag-detail',
    ),
    path(
        'oeffentlich/auftrag/<str:token>/bestaetigen/',
        OeffentlicherAuftragBestaetigenView.as_view(),
        name='oeffentlich-auftrag-bestaetigen',
    ),
]
