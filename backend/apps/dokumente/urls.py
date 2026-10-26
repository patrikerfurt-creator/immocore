from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DokumentViewSet
from .views_akten import (
    AktenregisterViewSet, DokumentEinsortierenView, EigentuemerakteView,
    HausakteView, KreditorakteView, RegistervorschlagView, WohnungsakteView,
)

router = DefaultRouter()
router.register(r'dokumente', DokumentViewSet, basename='dokumente')
router.register(r'aktenregister', AktenregisterViewSet, basename='aktenregister')

urlpatterns = router.urls + [
    path('akten/hausakte/', HausakteView.as_view(), name='akte-haus'),
    path('akten/wohnungsakte/', WohnungsakteView.as_view(), name='akte-wohnung'),
    path('akten/eigentuemerakte/', EigentuemerakteView.as_view(), name='akte-eigentuemer'),
    path('akten/kreditorenakte/', KreditorakteView.as_view(), name='akte-kreditor'),
    path('dokumente/<uuid:pk>/einsortieren/',
         DokumentEinsortierenView.as_view(), name='dokument-einsortieren'),
    path('dokumente/<uuid:pk>/registervorschlag/',
         RegistervorschlagView.as_view(), name='dokument-registervorschlag'),
]
