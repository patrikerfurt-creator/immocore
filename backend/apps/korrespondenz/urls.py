from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    BriefbogenViewSet, DruckstapelViewSet, PlatzhalterView, SchreibenViewSet, SerienlaufViewSet,
    TextbausteinViewSet, VersionViewSet, VorlageViewSet, VorlagenAssistentView,
)

router = SimpleRouter()
router.register('korrespondenz/schreiben', SchreibenViewSet, basename='korrespondenz-schreiben')
router.register('korrespondenz/druckstapel', DruckstapelViewSet, basename='korrespondenz-druckstapel')
router.register('korrespondenz/serienlaeufe', SerienlaufViewSet, basename='korrespondenz-serienlauf')
router.register('korrespondenz/vorlagen', VorlageViewSet, basename='korrespondenz-vorlage')
router.register('korrespondenz/versionen', VersionViewSet, basename='korrespondenz-version')
router.register('korrespondenz/textbausteine', TextbausteinViewSet, basename='korrespondenz-textbaustein')
router.register('korrespondenz/briefboegen', BriefbogenViewSet, basename='korrespondenz-briefbogen')

urlpatterns = [
    path('korrespondenz/platzhalter/', PlatzhalterView.as_view(), name='korrespondenz-platzhalter'),
    path('korrespondenz/vorlagen-assistent/', VorlagenAssistentView.as_view(),
         name='korrespondenz-vorlagen-assistent'),
    path('', include(router.urls)),
]
