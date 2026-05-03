from rest_framework.routers import DefaultRouter
from .views import DokumentViewSet

router = DefaultRouter()
router.register(r'dokumente', DokumentViewSet, basename='dokumente')

urlpatterns = router.urls
