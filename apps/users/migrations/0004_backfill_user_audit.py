from django.db import migrations


def backfill_user_creation(apps, schema_editor):
    User = apps.get_model('users', 'User')
    UserAuditLog = apps.get_model('users', 'UserAuditLog')
    for user in User.objects.select_related('created_by').order_by('id'):
        if UserAuditLog.objects.filter(
            target_id=user.id, action='created', source='backfill'
        ).exists():
            continue
        actor = user.created_by
        UserAuditLog.objects.create(
            action='created',
            actor=actor,
            actor_name=actor.full_name if actor else '',
            actor_email=actor.email if actor else '',
            actor_role=actor.role if actor else '',
            target=user,
            target_name=user.full_name,
            target_email=user.email,
            target_phone=user.phone,
            target_role=user.role,
            changes={'created': {'old': None, 'new': user.role}},
            source='backfill',
            created_at=user.created_at,
            note='Historical account creation backfill.',
        )


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0003_unique_phones'),
    ]

    operations = [
        migrations.RunPython(backfill_user_creation, migrations.RunPython.noop),
    ]
