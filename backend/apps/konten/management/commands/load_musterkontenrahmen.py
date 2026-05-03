from django.core.management.base import BaseCommand
from apps.konten.services import kontenrahmen_anlegen


class Command(BaseCommand):
    help = 'Legt Musterkontenrahmen WEG (70 Konten) für ein Objekt an.'

    def add_arguments(self, parser):
        parser.add_argument('--objekt', required=True, help='UUID des WEG-Objekts')

    def handle(self, *args, **options):
        objekt_id = options['objekt']
        try:
            result = kontenrahmen_anlegen(objekt_id)
            self.stdout.write(self.style.SUCCESS(
                f"Musterkontenrahmen angelegt: {result['angelegt']} neue Konten."
            ))
        except Exception as e:
            self.stderr.write(self.style.ERROR(str(e)))
