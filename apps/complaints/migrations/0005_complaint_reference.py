from zoneinfo import ZoneInfo

from django.db import migrations, models


def backfill_references(apps, schema_editor):
    Complaint = apps.get_model('complaints', 'Complaint')
    Sequence = apps.get_model('complaints', 'ComplaintReferenceSequence')
    ist = ZoneInfo('Asia/Kolkata')
    counters = {}

    for complaint in Complaint.objects.order_by('created_at', 'id'):
        local = complaint.created_at.astimezone(ist)
        period = f'{local.year:04d}-{local.month:02d}'
        value = counters.get(period, 0) + 1
        if value > 9999:
            raise RuntimeError(f'Complaint reference sequence exhausted for {period}.')
        counters[period] = value
        reference = f'CRM-{local.month:02d}-{local.year % 100:02d}-{value:04d}'
        Complaint.objects.filter(pk=complaint.pk).update(reference=reference)

    for period, value in counters.items():
        Sequence.objects.create(period=period, last_value=value)


class Migration(migrations.Migration):
    dependencies = [
        ('complaints', '0004_alter_complaint_geocode_status'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    'ALTER TABLE complaints ADD COLUMN reference varchar(15) NULL',
                    reverse_sql='ALTER TABLE complaints DROP COLUMN reference',
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name='complaint',
                    name='reference',
                    field=models.CharField(
                        editable=False,
                        max_length=15,
                        null=True,
                    ),
                )
            ],
        ),
        migrations.CreateModel(
            name='ComplaintReferenceSequence',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('period', models.CharField(max_length=7, unique=True)),
                ('last_value', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'complaint_reference_sequences'},
        ),
        migrations.RunPython(backfill_references, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    'CREATE UNIQUE INDEX complaints_reference_uniq ON complaints(reference)',
                    reverse_sql='DROP INDEX complaints_reference_uniq',
                )
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='complaint',
                    name='reference',
                    field=models.CharField(
                        editable=False, max_length=15, unique=True
                    ),
                )
            ],
        ),
    ]
