from rest_framework.routers import DefaultRouter
from .views import MitarbeiterViewSet, MitarbeiterObjektZuordnungViewSet

router = DefaultRouter()
router.register(r'mitarbeiter',            MitarbeiterViewSet,                basename='mitarbeiter')
router.register(r'mitarbeiter-zuordnungen', MitarbeiterObjektZuordnungViewSet, basename='mitarbeiter-zuordnungen')

urlpatterns = router.urls
