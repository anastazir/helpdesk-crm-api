import re

from django.db import migrations, models


def normalize(value):
    if not value:
        return ''
    value = re.sub(r'[\s\-()]', '', str(value))
    if value.startswith('+91'):
        value = value[3:]
    elif len(value) == 12 and value.startswith('91'):
        value = value[2:]
    return value if value.isdigit() and len(value) == 10 else ''


def populate_unique_phones(apps, schema_editor):
    User = apps.get_model('users', 'User')
    used = set()
    next_number = 9000000001

    for user in User.objects.order_by('id'):
        normalized = normalize(user.phone)
        if normalized and normalized not in used:
            phone = normalized
        else:
            while str(next_number) in used:
                next_number += 1
            phone = str(next_number)
            next_number += 1
        used.add(phone)
        if user.phone != phone:
            user.phone = phone
            user.save(update_fields=['phone'])


def add_unique_phone_index(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX users_phone_uniq ON users(phone)')


def remove_unique_phone_index(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP INDEX IF EXISTS users_phone_uniq')


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_user_lifecycle_and_audit'),
    ]

    operations = [
        migrations.RunPython(populate_unique_phones, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_unique_phone_index,
                    remove_unique_phone_index,
                )
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='user',
                    name='phone',
                    field=models.CharField(max_length=20, unique=True),
                )
            ],
        ),
    ]
