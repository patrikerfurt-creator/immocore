"""
Management-Command: konten_konsolidieren

Bereinigt doppelte Konto-Einträge innerhalb eines Objekts.
Problem: Durch Anwendung des Kontenrahmens auf mehrere Wirtschaftsjahre
entsteht pro kontonummer ein Konto-Datensatz je WJ — gleiche Kontonummern
erscheinen dann mehrfach in der UI.

Lösung:
  - Pro Kontonummer das älteste WJ als kanonisch behalten
  - Alle FK-Referenzen auf Duplikate automatisch auf das kanonische Konto umhängen
    (Buchungen, Unterkonten, BankMatchRegel, WpPositionen, RapPositionen, …)
  - Duplikate löschen

Aufruf:
  python manage.py konten_konsolidieren --objekt 10001
  python manage.py konten_konsolidieren --objekt 10001 --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction


def _get_konto_fk_felder():
    """Gibt alle (Model, ForeignKey-Feld-Name) zurück, die auf konten.Konto zeigen."""
    from django.apps import apps
    from apps.konten.models import Konto
    felder = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            # Nur direkte FK/O2O-Felder (haben 'column'), keine Reverse-Relations
            if (
                hasattr(field, 'column')
                and hasattr(field, 'remote_field')
                and field.remote_field is not None
                and getattr(field.remote_field, 'model', None) is Konto
            ):
                felder.append((model, field.name))
    return felder


class Command(BaseCommand):
    help = 'Konsolidiert doppelte Sachkonten eines Objekts (gleiche Kontonummer, mehrere WJ)'

    def add_arguments(self, parser):
        parser.add_argument('--objekt', required=True, help='Objektnummer, z.B. 10001')
        parser.add_argument('--dry-run', action='store_true', help='Nur anzeigen, nichts ändern')

    def handle(self, *args, **options):
        from apps.konten.models import Konto
        from apps.objekte.models import Objekt, Wirtschaftsjahr

        objektnummer = options['objekt']
        dry_run = options['dry_run']

        try:
            obj = Objekt.objects.get(objektnummer=objektnummer)
        except Objekt.DoesNotExist:
            self.stderr.write(f'Objekt {objektnummer!r} nicht gefunden.')
            return

        wjs = Wirtschaftsjahr.objects.filter(objekt=obj).order_by('jahr')
        self.stdout.write(f'Objekt {obj.objektnummer}: {obj.bezeichnung}')
        self.stdout.write(f'Wirtschaftsjahre: {[wj.jahr for wj in wjs]}')
        self.stdout.write('')

        # Alle FK-Felder auf Konto ermitteln
        fk_felder = _get_konto_fk_felder()
        self.stdout.write(f'Gefundene FK-Felder auf Konto: {len(fk_felder)}')
        for model, feldname in fk_felder:
            self.stdout.write(f'  {model.__name__}.{feldname}')
        self.stdout.write('')

        # Alle Konten des Objekts, ältestes WJ zuerst
        alle_konten = (
            Konto.objects.filter(wirtschaftsjahr__in=wjs)
            .select_related('wirtschaftsjahr')
            .order_by('kontonummer', 'wirtschaftsjahr__jahr')
        )

        # Gruppieren nach kontonummer
        gruppen: dict[str, list[Konto]] = {}
        for k in alle_konten:
            gruppen.setdefault(k.kontonummer, []).append(k)

        duplikate = {nr: ks for nr, ks in gruppen.items() if len(ks) > 1}

        if not duplikate:
            self.stdout.write(self.style.SUCCESS('Keine Duplikate gefunden.'))
            return

        self.stdout.write(f'Gefundene Duplikate: {len(duplikate)} Kontonummern')
        for nr, konten in duplikate.items():
            kanonisch = konten[0]
            rest = konten[1:]
            self.stdout.write(
                f'  {nr}: kanonisch=WJ {kanonisch.wirtschaftsjahr.jahr}, '
                f'löschen: {[f"WJ {k.wirtschaftsjahr.jahr}" for k in rest]}'
            )
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: Keine Änderungen vorgenommen.'))
            return

        # Bereinigung in einer Transaktion
        with transaction.atomic():
            geloescht_gesamt = 0
            refs_gesamt = 0

            for kontonummer, konten in duplikate.items():
                kanonisch = konten[0]   # ältestes WJ
                duplikate_konten = konten[1:]
                alte_ids = [k.id for k in duplikate_konten]

                # Alle FK-Referenzen auf duplikate_konten umhängen
                for model, feldname in fk_felder:
                    updated = model.objects.filter(
                        **{f'{feldname}__in': alte_ids}
                    ).update(**{feldname: kanonisch})
                    if updated:
                        refs_gesamt += updated
                        self.stdout.write(
                            f'  {kontonummer}: {model.__name__}.{feldname} '
                            f'— {updated} Zeile(n) umgehängt → WJ {kanonisch.wirtschaftsjahr.jahr}'
                        )

                # Duplikate löschen (CASCADE-Abhängigkeiten werden automatisch mitgelöscht)
                for k in duplikate_konten:
                    k.delete()
                    geloescht_gesamt += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Fertig: {geloescht_gesamt} Konto-Duplikate gelöscht, '
            f'{refs_gesamt} FK-Referenzen umgehängt.'
        ))
