from django.db import migrations, models

ANALYTICS_VIEWS = [
    """
    CREATE VIEW analytics_complaints AS
    SELECT c.id AS complaint_id, c.created_at, c.status, z.name AS zone,
           c.department, ca.engineer_id AS assigned_engineer_id,
           u.full_name AS assigned_engineer
    FROM complaints c
    LEFT JOIN zones z ON z.id = c.zone_id
    LEFT JOIN complaint_assignments ca
        ON ca.complaint_id = c.id AND ca.unassigned_at IS NULL
    LEFT JOIN users u ON u.id = ca.engineer_id
    """,
    """
    CREATE VIEW analytics_complaint_issues AS
    SELECT ci.complaint_id, i.id AS issue_id, i.name AS issue
    FROM complaints_issues ci
    JOIN issue_types i ON i.id = ci.issuetype_id
    """,
    """
    CREATE VIEW analytics_status_events AS
    SELECT id, complaint_id, previous_status, new_status, changed_at
    FROM status_history
    """,
    """
    CREATE VIEW analytics_assignments AS
    SELECT ca.id, ca.complaint_id, ca.engineer_id, u.full_name AS engineer,
           ca.assigned_at, ca.unassigned_at
    FROM complaint_assignments ca
    LEFT JOIN users u ON u.id = ca.engineer_id
    """,
]

VIEW_NAMES = [
    'analytics_complaints',
    'analytics_complaint_issues',
    'analytics_status_events',
    'analytics_assignments',
]


def drop_analytics_views(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for name in VIEW_NAMES:
            cursor.execute(f'DROP VIEW IF EXISTS {name}')


def create_analytics_views(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for statement in ANALYTICS_VIEWS:
            cursor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ('complaints', '0002_initial'),
        ('assistant', '0004_geocodecache'),
    ]

    operations = [
        migrations.RunPython(drop_analytics_views, migrations.RunPython.noop),
        migrations.AddField(
            model_name='complaint',
            name='address_remark',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='complaint',
            name='geocode_label',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='complaint',
            name='geocode_provider',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='complaint',
            name='geocode_status',
            field=models.CharField(
                choices=[
                    ('not_geocoded', 'Not geocoded'),
                    ('address', 'Address match'),
                    ('landmark', 'Landmark approximate'),
                    ('pincode', 'Pincode area'),
                    ('not_found', 'Not found'),
                    ('failed', 'Failed'),
                ],
                default='not_geocoded',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='complaint',
            name='geocode_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='complaint',
            name='latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='complaint',
            name='longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='complaint',
            name='map_radius_m',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(
            create_analytics_views,
            migrations.RunPython.noop,
        ),
    ]
