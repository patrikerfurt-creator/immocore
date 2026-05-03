from rest_framework.routers import DefaultRouter
from .views import AbrechnungsartViewSet, KontoViewSet, PersonenkontoViewSet, UnterkontoViewSet

router = DefaultRouter()
router.register(r'abrechnungsarten', AbrechnungsartViewSet, basename='abrechnungsarten')
router.register(r'konten', KontoViewSet, basename='konten')
router.register(r'personenkonten', PersonenkontoViewSet, basename='personenkonten')
router.register(r'unterkonten', UnterkontoViewSet, basename='unterkonten')

urlpatterns = router.urls
