from rest_framework.routers import DefaultRouter
from .views import ProzessViewSet

router = DefaultRouter()
router.register(r'prozesse', ProzessViewSet, basename='prozesse')

urlpatterns = router.urls
