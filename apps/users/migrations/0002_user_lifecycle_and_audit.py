from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def add_user_columns(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute(
                'ALTER TABLE users ADD COLUMN is_deleted boolean NOT NULL DEFAULT false'
            )
            cursor.execute(
                'ALTER TABLE users ADD COLUMN deleted_at timestamp with time zone NULL'
            )
            cursor.execute(
                'ALTER TABLE users ADD COLUMN deleted_by_id integer NULL '
                'REFERENCES users(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED'
            )
        else:
            cursor.execute(
                'ALTER TABLE users ADD COLUMN is_deleted bool NOT NULL DEFAULT 0'
            )
            cursor.execute(
                'ALTER TABLE users ADD COLUMN deleted_at datetime NULL'
            )
            cursor.execute(
                'ALTER TABLE users ADD COLUMN deleted_by_id integer NULL'
            )


def remove_user_columns(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute('ALTER TABLE users DROP COLUMN deleted_by_id')
            cursor.execute('ALTER TABLE users DROP COLUMN deleted_at')
            cursor.execute('ALTER TABLE users DROP COLUMN is_deleted')
        else:
            cursor.execute('ALTER TABLE users DROP COLUMN deleted_by_id')
            cursor.execute('ALTER TABLE users DROP COLUMN deleted_at')
            cursor.execute('ALTER TABLE users DROP COLUMN is_deleted')


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_user_columns, remove_user_columns),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='user',
                    name='is_deleted',
                    field=models.BooleanField(default=False),
                ),
                migrations.AddField(
                    model_name='user',
                    name='deleted_at',
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='user',
                    name='deleted_by',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='deleted_users',
                        to='users.user',
                    ),
                ),
            ],
        ),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('supervisor', 'Supervisor'),
                    ('helpdesk', 'Help Desk'),
                    ('engineer', 'Engineer'),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='UserAuditLog',
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
                (
                    'action',
                    models.CharField(
                        choices=[
                            ('created', 'Created'),
                            ('updated', 'Updated'),
                            ('password_changed', 'Password changed'),
                            ('disabled', 'Disabled'),
                            ('enabled', 'Enabled'),
                            ('deleted', 'Deleted'),
                            ('zone_added', 'Zone added'),
                            ('zone_removed', 'Zone removed'),
                        ],
                        max_length=30,
                    ),
                ),
                ('actor_name', models.CharField(blank=True, default='', max_length=255)),
                ('actor_email', models.EmailField(blank=True, default='', max_length=254)),
                ('actor_role', models.CharField(blank=True, default='', max_length=20)),
                ('target_name', models.CharField(blank=True, default='', max_length=255)),
                ('target_email', models.EmailField(blank=True, default='', max_length=254)),
                ('target_phone', models.CharField(blank=True, default='', max_length=20)),
                ('target_role', models.CharField(blank=True, default='', max_length=20)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('note', models.TextField(blank=True, default='')),
                (
                    'source',
                    models.CharField(
                        choices=[('live', 'Live'), ('backfill', 'Backfill')],
                        default='live',
                        max_length=10,
                    ),
                ),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                (
                    'actor',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='audit_actions_performed',
                        to='users.user',
                    ),
                ),
                (
                    'target',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='audit_actions_received',
                        to='users.user',
                    ),
                ),
            ],
            options={
                'db_table': 'user_audit_logs',
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
