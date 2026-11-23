from datetime import datetime, time
from io import BytesIO
from zoneinfo import ZoneInfo

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from apps.users.models import UserAuditLog

IST = ZoneInfo('Asia/Kolkata')
ACTION_FILLS = {
    'created': 'C6EFCE',
    'updated': 'DDEBF7',
    'password_changed': 'FFF2CC',
    'disabled': 'FCE4D6',
    'enabled': 'E2EFDA',
    'deleted': 'FFC7CE',
    'zone_added': 'E4DFEC',
    'zone_removed': 'F4CCCC',
}

AUDIT_HEADERS = [
    'Timestamp (IST)',
    'Action',
    'Actor Name',
    'Actor Email',
    'Actor Role',
    'Target Name',
    'Target Email',
    'Target Phone',
    'Target Role',
    'Changed Fields',
    'Old Values',
    'New Values',
    'Source',
    'Note',
]


def get_filtered_audit_logs(filters=None):
    filters = filters or {}
    queryset = UserAuditLog.objects.all().order_by('-created_at', '-id')
    action = filters.get('action')
    if action:
        queryset = queryset.filter(action=action)
    actor_id = filters.get('actor_id')
    if actor_id:
        queryset = queryset.filter(actor_id=actor_id)
    target_id = filters.get('target_id')
    if target_id:
        queryset = queryset.filter(target_id=target_id)
    search = (filters.get('search') or '').strip()
    if search:
        queryset = queryset.filter(
            target_name__icontains=search
        ) | queryset.filter(
            target_email__icontains=search
        ) | queryset.filter(
            target_phone__icontains=search
        )
    date_from = filters.get('date_from')
    if date_from:
        start = datetime.combine(date_from, time.min, tzinfo=IST)
        queryset = queryset.filter(created_at__gte=start)
    date_to = filters.get('date_to')
    if date_to:
        end = datetime.combine(date_to, time.max, tzinfo=IST)
        queryset = queryset.filter(created_at__lte=end)
    return queryset


def _changes_summary(log):
    fields = []
    old_values = []
    new_values = []
    for field, value in (log.changes or {}).items():
        fields.append(field)
        if isinstance(value, dict):
            old_values.append(f'{field}: {value.get("old")}')
            new_values.append(f'{field}: {value.get("new")}')
        else:
            old_values.append(f'{field}: ')
            new_values.append(f'{field}: {value}')
    return ', '.join(fields), '; '.join(old_values), '; '.join(new_values)


def audit_export_row(log):
    fields, old_values, new_values = _changes_summary(log)
    return {
        'timestamp': timezone.localtime(log.created_at, IST).strftime(
            '%Y-%m-%d %H:%M:%S'
        ),
        'action': log.get_action_display(),
        'action_key': log.action,
        'actor_name': log.actor_name,
        'actor_email': log.actor_email,
        'actor_role': log.actor_role,
        'target_name': log.target_name,
        'target_email': log.target_email,
        'target_phone': log.target_phone,
        'target_role': log.target_role,
        'changed_fields': fields,
        'old_values': old_values,
        'new_values': new_values,
        'source': log.source,
        'note': log.note,
    }


def build_audit_workbook(logs):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'User Audit'
    header_font = Font(bold=True)
    for index, header in enumerate(AUDIT_HEADERS, start=1):
        cell = worksheet.cell(row=1, column=index, value=header)
        cell.font = header_font
    keys = [
        'timestamp',
        'action',
        'actor_name',
        'actor_email',
        'actor_role',
        'target_name',
        'target_email',
        'target_phone',
        'target_role',
        'changed_fields',
        'old_values',
        'new_values',
        'source',
        'note',
    ]
    for row_index, log in enumerate(logs, start=2):
        row = audit_export_row(log)
        fill = PatternFill(
            start_color=ACTION_FILLS.get(log.action, 'FFFFFF'),
            end_color=ACTION_FILLS.get(log.action, 'FFFFFF'),
            fill_type='solid',
        )
        for column_index, key in enumerate(keys, start=1):
            cell = worksheet.cell(
                row=row_index, column=column_index, value=row[key]
            )
            cell.fill = fill
    for column_index in range(1, len(AUDIT_HEADERS) + 1):
        worksheet.column_dimensions[
            worksheet.cell(row=1, column=column_index).column_letter
        ].width = 24
    return workbook


def audit_preview_payload(logs):
    total = logs.count()
    rows = [audit_export_row(log) for log in logs[:10]]
    return {
        'total_matching': total,
        'columns': AUDIT_HEADERS,
        'rows': rows,
    }
