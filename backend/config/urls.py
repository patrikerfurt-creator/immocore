from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    user = request.user
    gruppen = list(user.groups.values_list('name', flat=True))
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'vorname': user.first_name,
        'nachname': user.last_name,
        'vollname': user.get_full_name(),
        'gruppen': gruppen,
        'is_superuser': user.is_superuser,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def iban_check(request):
    iban_raw = request.query_params.get('iban', '').replace(' ', '').upper()
    if not iban_raw:
        return Response({'valid': False, 'error': 'Keine IBAN angegeben'})
    try:
        from schwifty import IBAN
        iban = IBAN(iban_raw)
        bic = ''
        bank_name = ''
        try:
            bic_obj = iban.bic
            if bic_obj:
                bic = str(bic_obj)
                bank_name = getattr(bic_obj, 'bank_name', '') or ''
        except Exception:
            pass
        return Response({'valid': True, 'iban': str(iban), 'bic': bic, 'bank_name': bank_name})
    except Exception as e:
        return Response({'valid': False, 'error': str(e)})

API_PREFIX = 'api/v1/'

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path(API_PREFIX + 'auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path(API_PREFIX + 'auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Import-Seiten
    path('import/einheiten/', login_required(lambda req: render(req, 'einheiten_import.html')), name='einheiten-import'),
    path('import/konten/', login_required(lambda req: render(req, 'konten_import.html')), name='konten-import'),

    # Browsable API Login (nur im DEBUG-Modus genutzt)
    path('api-auth/', include('rest_framework.urls')),

    # Apps
    path(API_PREFIX, include('apps.objekte.urls')),
    path(API_PREFIX, include('apps.personen.urls')),
    path(API_PREFIX, include('apps.konten.urls')),
    path(API_PREFIX, include('apps.buchhaltung.urls')),
    path(API_PREFIX, include('apps.rechnungen.urls')),
    path(API_PREFIX, include('apps.prozesse.urls')),
    path(API_PREFIX, include('apps.dokumente.urls')),
    path(API_PREFIX, include('apps.tickets.urls')),
    path(API_PREFIX, include('apps.massenimport.urls')),
    path(API_PREFIX, include('apps.mitarbeiter.urls')),
    path(API_PREFIX + 'iban-check/', iban_check, name='iban-check'),
    path(API_PREFIX + 'me/', me_view, name='me'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
