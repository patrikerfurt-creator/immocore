from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.objekte.models import Objekt
from .models import VerteilerImportProtokoll
from .services.verteiler.export_service import (
    ermittle_aktive_vs, export_verteiler_zip, VsExportRequest,
)
from .services.verteiler.import_service import (
    parse_vs_datei, erstelle_preview, commit_verteiler_import, ParseError,
)


def _get_objekt(objekt_id) -> Objekt | None:
    try:
        return Objekt.objects.get(id=objekt_id)
    except Objekt.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# GET /api/v1/objekte/{objekt_id}/verteiler/aktive-vs/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def aktive_vs_view(request, objekt_id):
    objekt = _get_objekt(objekt_id)
    if not objekt:
        return Response({'error': 'Objekt nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

    vs_liste = ermittle_aktive_vs(objekt)
    return Response([
        {
            'code':          vs.code,
            'bezeichnung':   vs.bezeichnung,
            'kategorie':     vs.kategorie,
            'wirtschaftsjahre': vs.wirtschaftsjahre,
        }
        for vs in vs_liste
    ])


# ---------------------------------------------------------------------------
# POST /api/v1/objekte/{objekt_id}/verteiler/export/
# Body: { vs_codes: [{code, wj_id?}, ...] }
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_view(request, objekt_id):
    objekt = _get_objekt(objekt_id)
    if not objekt:
        return Response({'error': 'Objekt nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

    rohdaten = request.data.get('vs_codes', [])
    if not rohdaten:
        return Response(
            {'error': 'Bitte mindestens einen Verteilerschlüssel auswählen.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        anforderungen = [
            VsExportRequest(code=item['code'], wj_id=item.get('wj_id'))
            for item in rohdaten
        ]
        zip_bytes = export_verteiler_zip(objekt, anforderungen)
    except (ValueError, KeyError) as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    from django.utils import timezone
    ts = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')
    filename = f"VS_Export_{objekt.objektnummer}_{ts}.zip"

    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# POST /api/v1/objekte/{objekt_id}/verteiler/import/preview/
# multipart: datei=<file>
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def import_preview_view(request, objekt_id):
    objekt = _get_objekt(objekt_id)
    if not objekt:
        return Response({'error': 'Objekt nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

    datei = request.FILES.get('datei')
    if not datei:
        return Response({'error': 'Datei fehlt.'}, status=status.HTTP_400_BAD_REQUEST)

    if datei.size > 5 * 1024 * 1024:
        return Response({'error': 'Datei zu groß.'}, status=status.HTTP_400_BAD_REQUEST)

    if not datei.name.lower().endswith('.xlsx'):
        return Response(
            {'error': 'Nur .xlsx-Dateien erlaubt.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed = parse_vs_datei(datei.read(), datei.name, objekt)
    except ParseError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    _token, vorschau = erstelle_preview(parsed, objekt, request.user)
    return Response(vorschau)


# ---------------------------------------------------------------------------
# POST /api/v1/objekte/{objekt_id}/verteiler/import/commit/
# Body: { preview_token: "..." }
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_commit_view(request, objekt_id):
    objekt = _get_objekt(objekt_id)
    if not objekt:
        return Response({'error': 'Objekt nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

    token = request.data.get('preview_token')
    if not token:
        return Response({'error': 'preview_token fehlt.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = commit_verteiler_import(token, request.user)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(result)


# ---------------------------------------------------------------------------
# GET /api/v1/objekte/{objekt_id}/verteiler/protokoll/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def protokoll_view(request, objekt_id):
    objekt = _get_objekt(objekt_id)
    if not objekt:
        return Response({'error': 'Objekt nicht gefunden.'}, status=status.HTTP_404_NOT_FOUND)

    eintraege = (
        VerteilerImportProtokoll.objects
        .filter(objekt=objekt)
        .select_related('wirtschaftsjahr', 'importiert_von')
        .order_by('-importiert_am')
    )
    return Response([
        {
            'id':                   str(e.id),
            'vs_code':              e.vs_code,
            'dateiname':            e.dateiname,
            'wj_jahr':              e.wirtschaftsjahr.jahr if e.wirtschaftsjahr else None,
            'anzahl_aktualisiert':  e.anzahl_aktualisiert,
            'importiert_am':        e.importiert_am.isoformat(),
            'importiert_von':       e.importiert_von.get_full_name() or e.importiert_von.username,
        }
        for e in eintraege
    ])
