from django.db import migrations

VIEWS = {
    'analytics_complaints': '''
        CREATE VIEW analytics_complaints AS
        SELECT
            c.id AS complaint_id,
            c.created_at,
            c.status,
            z.name AS zone,
            c.department,
            ca.engineer_id AS assigned_engineer_id,
            u.full_name AS assigned_engineer
        FROM complaints c
        LEFT JOIN zones z ON z.id = c.zone_id
        LEFT JOIN complaint_assignments ca
            ON ca.complaint_id = c.id AND ca.unassigned_at IS NULL
        LEFT JOIN users u ON u.id = ca.engineer_id
    ''',
    'analytics_complaint_issues': '''
        CREATE VIEW analytics_complaint_issues AS
        SELECT
            ci.complaint_id,
            i.id AS issue_id,
            i.name AS issue
        FROM complaints_issues ci
        JOIN issue_types i ON i.id = ci.issuetype_id
    ''',
    'analytics_status_events': '''
        CREATE VIEW analytics_status_events AS
        SELECT
            sh.id,
            sh.complaint_id,
            sh.previous_status,
            sh.new_status,
            sh.changed_at
        FROM status_history sh
    ''',
    'analytics_assignments': '''
        CREATE VIEW analytics_assignments AS
        SELECT
            ca.id,
            ca.complaint_id,
            ca.engineer_id,
            u.full_name AS engineer,
            ca.assigned_at,
            ca.unassigned_at
        FROM complaint_assignments ca
        LEFT JOIN users u ON u.id = ca.engineer_id
    ''',
}


def create_views(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for name in VIEWS:
            cursor.execute(f'DROP VIEW IF EXISTS {name}')
        for statement in VIEWS.values():
            cursor.execute(statement)


def drop_views(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for name in reversed(list(VIEWS)):
            cursor.execute(f'DROP VIEW IF EXISTS {name}')


class Migration(migrations.Migration):
    dependencies = [
        ('assistant', '0001_initial'),
        ('complaints', '0002_initial'),
        ('users', '0001_initial'),
        ('zones', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_views, drop_views),
    ]
