from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    KreditorViewSet, RechnungViewSet, FreigabeViewSet,
    FreigabelimitDefaultView, RechnungsMatchRegelViewSet,
)
from .views_dubletten import KreditorDublettenPruefungViewSet

router = DefaultRouter()
router.register(r'kreditor-dubletten', KreditorDublettenPruefungViewSet,
                basename='kreditor-dubletten')
router.register(r'kreditoren',    KreditorViewSet,           basename='kreditoren')
router.register(r'rechnungen',    RechnungViewSet,           basename='rechnungen')
router.register(r'freigaben',     FreigabeViewSet,           basename='freigaben')
router.register(r'match-regeln',  RechnungsMatchRegelViewSet, basename='match-regeln')

urlpatterns = router.urls + [
    path('freigabelimits-standard/', FreigabelimitDefaultView.as_view(), name='freigabelimits-standard'),
]
