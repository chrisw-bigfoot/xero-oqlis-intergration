from django.core.management.base import BaseCommand
from xero.models import DatasetType


class Command(BaseCommand):
    help = 'Initialize default dataset types for Xero imports'

    def handle(self, *args, **options):
        dataset_types = [
            {
                'name': 'invoices',
                'display_name': 'Invoices',
                'description': 'Customer invoices - accounts receivable transactions'
            },
            {
                'name': 'bills',
                'display_name': 'Bills',
                'description': 'Supplier bills - accounts payable transactions'
            },
            {
                'name': 'contacts',
                'display_name': 'Contacts',
                'description': 'Customers and suppliers contact information'
            },
            {
                'name': 'accounts',
                'display_name': 'Chart of Accounts',
                'description': 'General ledger account structure'
            },
            {
                'name': 'journal_entries',
                'display_name': 'Journal Entries',
                'description': 'General ledger journal entries'
            },
        ]

        created_count = 0
        for dt in dataset_types:
            obj, created = DatasetType.objects.get_or_create(
                name=dt['name'],
                defaults={
                    'display_name': dt['display_name'],
                    'description': dt['description']
                }
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created: {obj.display_name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'→ Already exists: {obj.display_name}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nDataset types initialization complete! ({created_count} new records)')
        )
