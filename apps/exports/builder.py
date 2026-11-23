import logging

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.complaints.models import Complaint

from .serializers import COLUMN_HEADERS

logger = logging.getLogger('apps.exports')


def apply_filters(queryset, filters):
    filters = filters or {}

    zone_id = filters.get('zone_id')
    zone_ids = filters.get('zone_ids') or []
    if zone_ids:
        queryset = queryset.filter(zone_id__in=zone_ids)
    elif zone_id is not None:
        queryset = queryset.filter(zone_id=zone_id)

    status_value = filters.get('status')
    statuses = filters.get('statuses') or []
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    elif status_value:
        queryset = queryset.filter(status=status_value)

    date_from = filters.get('date_from')
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)

    date_to = filters.get('date_to')
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    assigned_engineer_id = filters.get('assigned_engineer_id')
    assigned_engineer_ids = filters.get('assigned_engineer_ids') or []
    if assigned_engineer_ids:
        queryset = queryset.filter(
            assignments__engineer_id__in=assigned_engineer_ids,
            assignments__unassigned_at__isnull=True,
        ).distinct()
    elif assigned_engineer_id is not None:
        queryset = queryset.filter(
            assignments__engineer_id=assigned_engineer_id,
            assignments__unassigned_at__isnull=True,
        ).distinct()

    cpu_serial_contains = filters.get('cpu_serial_contains')
    if cpu_serial_contains:
        queryset = queryset.filter(cpu_serial__icontains=cpu_serial_contains)

    return queryset


def deduplicate_complaints(queryset):
    complaints = list(queryset)
    newest_by_serial = {}
    without_serial = []

    for complaint in complaints:
        serial = (complaint.cpu_serial or '').strip()
        if not serial:
            without_serial.append(complaint)
            continue
        existing = newest_by_serial.get(serial)
        if existing is None or complaint.id > existing.id:
            newest_by_serial[serial] = complaint

    kept = list(newest_by_serial.values()) + without_serial
    kept.sort(key=lambda complaint: complaint.id)
    return kept


def get_matching_complaints(filters=None, deduplicate=False):
    queryset = apply_filters(
        Complaint.objects.select_related('zone', 'created_by').prefetch_related('issues'),
        filters,
    )
    if deduplicate:
        return deduplicate_complaints(queryset.order_by('id'))
    return list(queryset.order_by('id'))


def format_time_open(seconds):
    total_seconds = int(seconds)
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    return f'{days} days {hours} hours'


def get_column_value(complaint, column):
    if column == 'id':
        return complaint.reference
    if column == 'caller_name':
        return complaint.caller_name or ''
    if column == 'caller_phone':
        return complaint.caller_phone or ''
    if column == 'zone':
        return complaint.zone.name if complaint.zone else ''
    if column == 'issues':
        return ', '.join(issue.name for issue in complaint.issues.all())
    if column == 'status':
        return complaint.get_status_display()
    if column == 'assigned_engineer':
        engineer = complaint.get_assigned_engineer()
        return engineer.full_name if engineer else ''
    if column == 'cpu_serial':
        return complaint.cpu_serial or ''
    if column == 'monitor_serial':
        return complaint.monitor_serial or ''
    if column == 'created_at':
        return timezone.localtime(complaint.created_at).strftime('%Y-%m-%d %H:%M')
    if column == 'time_open':
        return format_time_open(complaint.get_time_open_seconds())
    if column == 'department':
        return complaint.department or ''
    if column == 'designation':
        return complaint.designation or ''
    if column == 'bmid':
        return complaint.bmid or ''
    if column == 'address':
        return complaint.address or ''
    if column == 'pincode':
        return complaint.pincode or ''
    return ''


def build_workbook(complaints, columns):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Complaints'

    header_font = Font(bold=True)
    for column_index, column in enumerate(columns, start=1):
        cell = worksheet.cell(row=1, column=column_index, value=COLUMN_HEADERS[column])
        cell.font = header_font

    for row_index, complaint in enumerate(complaints, start=2):
        for column_index, column in enumerate(columns, start=1):
            worksheet.cell(
                row=row_index,
                column=column_index,
                value=get_column_value(complaint, column),
            )

    for column_index, column in enumerate(columns, start=1):
        max_length = len(str(COLUMN_HEADERS[column]))
        for row_index in range(2, len(complaints) + 2):
            value = worksheet.cell(row=row_index, column=column_index).value
            if value is not None:
                max_length = max(max_length, len(str(value)))
        worksheet.column_dimensions[
            worksheet.cell(row=1, column=column_index).column_letter
        ].width = min(max_length + 2, 60)

    return workbook
