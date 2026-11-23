from django.db import migrations


MCD_STAFF_VIEWS = {
    'analytics_complaints': '''
        SELECT
            c.id AS complaint_id,
            c.created_at,
            c.status,
            z.name AS zone,
            c.department,
            ca.engineer_id AS assigned_engineer_id,
            u.full_name AS assigned_engineer,
            c.created_by_id,
            creator.full_name AS created_by_name,
            creator.role AS created_by_role
        FROM complaints c
        LEFT JOIN zones z ON z.id = c.zone_id
        LEFT JOIN complaint_assignments ca
            ON ca.complaint_id = c.id AND ca.unassigned_at IS NULL
        LEFT JOIN users u ON u.id = ca.engineer_id
        LEFT JOIN users creator ON creator.id = c.created_by_id
    ''',
    'analytics_complaint_issues': '''
        SELECT
            ci.complaint_id,
            i.id AS issue_id,
            i.name AS issue
        FROM complaints_issues ci
        JOIN issue_types i ON i.id = ci.issuetype_id
    ''',
    'analytics_status_events': '''
        SELECT
            sh.id,
            sh.complaint_id,
            sh.previous_status,
            sh.new_status,
            sh.changed_at,
            sh.changed_by_id,
            actor.full_name AS changed_by_name,
            actor.role AS changed_by_role
        FROM status_history sh
        LEFT JOIN users actor ON actor.id = sh.changed_by_id
    ''',
    'analytics_assignments': '''
        SELECT
            ca.id,
            ca.complaint_id,
            ca.engineer_id,
            u.full_name AS engineer,
            ca.assigned_at,
            ca.unassigned_at,
            ca.assigned_by_id,
            assigner.full_name AS assigned_by_name,
            assigner.role AS assigned_by_role,
            ca.unassigned_by_id,
            unassigner.full_name AS unassigned_by_name,
            unassigner.role AS unassigned_by_role
        FROM complaint_assignments ca
        LEFT JOIN users u ON u.id = ca.engineer_id
        LEFT JOIN users assigner ON assigner.id = ca.assigned_by_id
        LEFT JOIN users unassigner ON unassigner.id = ca.unassigned_by_id
    ''',
}

OLD_VIEWS = {
    'analytics_complaints': '''
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
    'analytics_complaint_issues': MCD_STAFF_VIEWS['analytics_complaint_issues'],
    'analytics_status_events': '''
        SELECT
            sh.id,
            sh.complaint_id,
            sh.previous_status,
            sh.new_status,
            sh.changed_at
        FROM status_history sh
    ''',
    'analytics_assignments': '''
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


def _apply_views(schema_editor, views):
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == 'postgresql':
            for name, select in views.items():
                cursor.execute(f'CREATE OR REPLACE VIEW {name} AS {select}')
            return
        for name in views:
            cursor.execute(f'DROP VIEW IF EXISTS {name}')
        for name, select in views.items():
            cursor.execute(f'CREATE VIEW {name} AS {select}')


def add_staff_fields(apps, schema_editor):
    _apply_views(schema_editor, MCD_STAFF_VIEWS)


def remove_staff_fields(apps, schema_editor):
    _apply_views(schema_editor, OLD_VIEWS)


class Migration(migrations.Migration):
    dependencies = [
        ('assistant', '0006_assistantsettings'),
    ]

    operations = [
        migrations.RunPython(add_staff_fields, remove_staff_fields),
    ]
