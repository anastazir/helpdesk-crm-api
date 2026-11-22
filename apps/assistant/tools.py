import logging
from datetime import timedelta, timezone as datetime_timezone

from django.db.models import Count, Q
from django.utils import timezone

from apps.complaints.models import Complaint, ComplaintAssignment

logger = logging.getLogger('apps.assistant')
IST = datetime_timezone(timedelta(hours=5, minutes=30))

STATUS_NAMES = [
    'open',
    'assigned',
    'in_progress',
    'parts_requested',
    'parts_provided',
    'resolved',
    'closed',
]
STATUS_LABELS = {
    'open': 'Open',
    'assigned': 'Assigned',
    'in_progress': 'In Progress',
    'parts_requested': 'Parts Requested',
    'parts_provided': 'Parts Provided',
    'resolved': 'Resolved',
    'closed': 'Closed',
}


class ToolError(Exception):
    pass


class ToolPermissionError(ToolError):
    pass


class ToolNotFoundError(ToolError):
    pass


def can_view_complaint(user, complaint):
    if user.role in ('admin', 'helpdesk'):
        return True
    assignment = complaint.get_current_assignment()
    return assignment is not None and assignment.engineer_id == user.id


def is_assigned_to(user, complaint):
    assignment = complaint.get_current_assignment()
    return assignment is not None and assignment.engineer_id == user.id


def scoped_complaints(user):
    queryset = Complaint.objects.all()
    if user.role == 'engineer':
        queryset = queryset.filter(
            assignments__engineer=user,
            assignments__unassigned_at__isnull=True,
        ).distinct()
    return queryset


def status_label(status):
    return STATUS_LABELS.get(status, status)


def build_complaint_context(complaint):
    assignment = complaint.get_current_assignment()
    history = list(
        complaint.status_history.select_related('changed_by').order_by(
            'changed_at', 'id'
        )[:200]
    )
    assignments = list(
        complaint.assignments.select_related(
            'engineer', 'assigned_by', 'unassigned_by'
        ).order_by('assigned_at', 'id')[:100]
    )
    uploads = list(complaint.uploads.values_list('file_type', flat=True))
    now = timezone.now()
    created_at_ist = complaint.created_at.astimezone(IST)

    def profile(user):
        return (
            {'name': user.full_name, 'role': user.role}
            if user
            else None
        )

    def history_entry(entry):
        changed_at_ist = entry.changed_at.astimezone(IST)
        changed_by = entry.changed_by
        return {
            'previous_status': entry.previous_status,
            'previous_status_label': (
                status_label(entry.previous_status)
                if entry.previous_status
                else None
            ),
            'status': entry.new_status,
            'status_label': status_label(entry.new_status),
            'changed_at': entry.changed_at.isoformat(),
            'changed_at_ist': changed_at_ist.strftime(
                '%d %b %Y, %I:%M %p IST'
            ),
            'changed_by': changed_by.full_name if changed_by else None,
            'changed_by_role': changed_by.role if changed_by else None,
            'remark': entry.remark,
        }

    def assignment_entry(entry):
        assigned_at_ist = entry.assigned_at.astimezone(IST)
        unassigned_at_ist = (
            entry.unassigned_at.astimezone(IST)
            if entry.unassigned_at
            else None
        )
        return {
            'engineer': profile(entry.engineer),
            'assigned_at': entry.assigned_at.isoformat(),
            'assigned_at_ist': assigned_at_ist.strftime(
                '%d %b %Y, %I:%M %p IST'
            ),
            'assigned_by': profile(entry.assigned_by),
            'unassigned_at': (
                entry.unassigned_at.isoformat()
                if entry.unassigned_at
                else None
            ),
            'unassigned_at_ist': (
                unassigned_at_ist.strftime('%d %b %Y, %I:%M %p IST')
                if unassigned_at_ist
                else None
            ),
            'unassigned_by': profile(entry.unassigned_by),
        }

    job_note = getattr(complaint, 'job_note', None)
    return {
        'id': complaint.id,
        'status': complaint.status,
        'status_label': status_label(complaint.status),
        'zone': complaint.zone.name if complaint.zone else None,
        'issues': list(complaint.issues.values_list('name', flat=True)),
        'others_description': complaint.others_description,
        'department': complaint.department,
        'designation': complaint.designation,
        'created_at': complaint.created_at.isoformat(),
        'created_at_ist': created_at_ist.strftime('%d %b %Y, %I:%M %p IST'),
        'created_by': profile(complaint.created_by),
        'age_hours': round(
            (now - complaint.created_at).total_seconds() / 3600,
            1,
        ),
        'time_in_status_hours': round(
            complaint.get_time_in_status_seconds() / 3600,
            1,
        ),
        'assigned_engineer': (
            profile(assignment.engineer) if assignment else None
        ),
        'job_note': job_note.text if job_note else None,
        'job_note_created_by': profile(job_note.created_by) if job_note else None,
        'uploads_count': len(uploads),
        'upload_types': sorted(set(uploads)),
        'comments_count': complaint.comments.count(),
        'assignment_count': complaint.assignments.count(),
        'assignments': [assignment_entry(entry) for entry in assignments],
        'status_history_count': len(history),
        'status_history': [history_entry(entry) for entry in history],
        'recent_status_history': [
            history_entry(entry) for entry in reversed(history[-8:])
        ],
    }


def complaint_summary(user, complaint):
    assignment = complaint.get_current_assignment()
    created_by = complaint.created_by
    return {
        'id': complaint.id,
        'status': complaint.status,
        'status_label': status_label(complaint.status),
        'zone': complaint.zone.name if complaint.zone else None,
        'issues': list(complaint.issues.values_list('name', flat=True)),
        'created_at': complaint.created_at.isoformat(),
        'age_days': max(
            0,
            int((timezone.now() - complaint.created_at).total_seconds() // 86400),
        ),
        'created_by': (
            {'name': created_by.full_name, 'role': created_by.role}
            if created_by
            else None
        ),
        'assigned_engineer': (
            assignment.engineer.full_name if assignment else None
        ),
    }


def _parse_limit(value, default=10, maximum=20):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _parse_optional_int(value, minimum=0, maximum=365):
    if value is None or value == '':
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ToolError('Expected an integer value.')
    return max(minimum, min(parsed, maximum))


def _parse_statuses(value):
    if not value:
        return []
    if isinstance(value, str):
        values = [item.strip() for item in value.split(',') if item.strip()]
    elif isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise ToolError('Statuses must be a list.')
    invalid = [item for item in values if item not in STATUS_NAMES]
    if invalid:
        raise ToolError(
            f"Unknown status: {', '.join(invalid)}. "
            f"Use one of: {', '.join(STATUS_NAMES)}."
        )
    return values


def search_complaints(user, args):
    queryset = scoped_complaints(user).select_related(
        'zone', 'created_by'
    ).prefetch_related('issues')
    query = str(args.get('query') or '').strip()
    statuses = _parse_statuses(args.get('statuses'))
    zone = str(args.get('zone') or '').strip()
    engineer = str(args.get('engineer') or '').strip()
    older_than_days = _parse_optional_int(args.get('older_than_days'))
    newer_than_days = _parse_optional_int(args.get('newer_than_days'))
    created_within_hours = _parse_optional_int(
        args.get('created_within_hours'), minimum=1, maximum=8760
    )
    ordering = args.get('ordering') or 'newest'
    limit = _parse_limit(args.get('limit'), default=10, maximum=20)

    if query:
        if query.isdigit():
            queryset = queryset.filter(id=int(query))
        elif user.role in ('admin', 'helpdesk'):
            queryset = queryset.filter(
                Q(caller_name__icontains=query)
                | Q(caller_phone__icontains=query)
            )
        else:
            queryset = queryset.none()
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    if zone:
        queryset = queryset.filter(zone__name__icontains=zone)
    if engineer and user.role in ('admin', 'helpdesk'):
        queryset = queryset.filter(
            assignments__engineer__full_name__icontains=engineer,
            assignments__unassigned_at__isnull=True,
        ).distinct()
    if older_than_days is not None:
        queryset = queryset.filter(
            created_at__lt=timezone.now() - timedelta(days=older_than_days)
        )
    if newer_than_days is not None:
        queryset = queryset.filter(
            created_at__gte=timezone.now() - timedelta(days=newer_than_days)
        )
    if created_within_hours is not None:
        queryset = queryset.filter(
            created_at__gte=timezone.now() - timedelta(hours=created_within_hours)
        )

    if ordering == 'oldest':
        queryset = queryset.order_by('created_at')
    else:
        queryset = queryset.order_by('-created_at')

    count = queryset.count()
    complaints = [
        complaint_summary(user, complaint)
        for complaint in queryset[:limit]
    ]
    return {
        'count': count,
        'returned': len(complaints),
        'complaints': complaints,
    }


def get_complaint(user, args):
    complaint_id = args.get('complaint_id')
    if complaint_id is None:
        raise ToolError('complaint_id is required.')
    try:
        complaint = Complaint.objects.select_related(
            'zone', 'job_note', 'job_note__created_by', 'created_by'
        ).prefetch_related(
            'issues',
            'uploads',
            'status_history',
            'assignments__engineer',
            'comments',
        ).get(pk=int(complaint_id))
    except (TypeError, ValueError):
        raise ToolError('complaint_id must be an integer.')
    except Complaint.DoesNotExist:
        raise ToolNotFoundError(f'Complaint {complaint_id} was not found.')

    if not can_view_complaint(user, complaint):
        raise ToolPermissionError('You do not have access to this complaint.')
    return {'complaint': build_complaint_context(complaint)}


def get_engineer_workload(user, args):
    if user.role not in ('admin', 'helpdesk'):
        raise ToolPermissionError(
            'Engineer workload is available to Admin and Help Desk only.'
        )
    rows = (
        ComplaintAssignment.objects.filter(
            unassigned_at__isnull=True,
            engineer__is_active=True,
        )
        .exclude(complaint__status='closed')
        .values('engineer__full_name')
        .annotate(active=Count('id'))
        .order_by('-active', 'engineer__full_name')[:10]
    )
    return {
        'engineers': [
            {'engineer': row['engineer__full_name'], 'active': row['active']}
            for row in rows
        ]
    }


def get_sla_risks(user, args):
    days = 7
    limit = _parse_limit(args.get('limit'), default=10, maximum=20)
    queryset = (
        scoped_complaints(user)
        .select_related('zone')
        .prefetch_related('issues')
        .exclude(status='closed')
        .filter(created_at__lt=timezone.now() - timedelta(days=days))
        .order_by('created_at')
    )
    count = queryset.count()
    complaints = [
        complaint_summary(user, complaint)
        for complaint in queryset[:limit]
    ]
    return {
        'days': days,
        'count': count,
        'complaints': complaints,
    }


def get_parts_queue(user, args):
    limit = _parse_limit(args.get('limit'), default=10, maximum=20)
    queryset = (
        scoped_complaints(user)
        .select_related('zone')
        .prefetch_related('issues')
        .filter(status__in=['parts_requested', 'parts_provided'])
        .order_by('created_at')
    )
    count = queryset.count()
    complaints = [
        complaint_summary(user, complaint)
        for complaint in queryset[:limit]
    ]
    return {
        'count': count,
        'complaints': complaints,
    }


def run_analytics_query(user, args):
    if user.role != 'admin':
        raise ToolPermissionError(
            'SQL analytics is available to admins only.'
        )
    from .analytics import AnalyticsError, execute_analytics_sql

    sql = args.get('sql')
    if not isinstance(sql, str) or not sql.strip():
        raise ToolError('SQL is required.')
    try:
        return execute_analytics_sql(sql, max_rows=100)
    except AnalyticsError as exc:
        from .analytics import analytics_dialect

        dialect = analytics_dialect()
        hint = (
            "Use datetime('now', '-2 hours') or date('now', '-7 days') "
            'and date(created_at); never use INTERVAL.'
            if dialect == 'sqlite'
            else "Use now() - interval '2 hours' or "
            "current_date - interval '7 days'."
        )
        return {
            'error': str(exc),
            'dialect': dialect,
            'hint': hint,
        }


def get_operations_summary(user, args):
    if user.role not in ('admin', 'helpdesk'):
        raise ToolPermissionError(
            'The operations summary is available to Admin and Help Desk only.'
        )
    from .services import build_briefing_context

    return build_briefing_context()


def execute_tool(user, name, arguments):
    handlers = {
        'get_operations_summary': (get_operations_summary, True),
        'run_analytics_query': (run_analytics_query, False),
        'search_complaints': (search_complaints, False),
        'get_complaint': (get_complaint, False),
        'get_engineer_workload': (get_engineer_workload, False),
        'get_sla_risks': (get_sla_risks, False),
        'get_parts_queue': (get_parts_queue, False),
    }
    handler = handlers.get(name)
    if handler is None:
        return {'error': f'Unknown tool: {name}.'}

    args = arguments if isinstance(arguments, dict) else {}
    logger.info('[AI TOOL] user=%s tool=%s', user.id, name)
    try:
        return handler[0](user, args)
    except ToolError as exc:
        return {'error': str(exc)}
    except Exception:
        logger.exception('[AI TOOL] Unexpected failure in %s', name)
        return {'error': 'The data lookup failed.'}


def extract_references(tool_name, result):
    references = []
    for complaint in result.get('complaints', []) or []:
        references.append(
            {
                'id': complaint['id'],
                'label': (
                    f"#{complaint['id']} · {complaint['status_label']}"
                    f" · {complaint.get('zone') or 'No zone'}"
                ),
            }
        )
    complaint = result.get('complaint')
    if complaint:
        references.append(
            {
                'id': complaint['id'],
                'label': (
                    f"#{complaint['id']} · {complaint['status_label']}"
                    f" · {complaint.get('zone') or 'No zone'}"
                ),
            }
        )
    if tool_name == 'get_operations_summary':
        for item in result.get('sla_risk_complaints', []) or []:
            references.append(
                {
                    'id': item['id'],
                    'label': (
                        f"#{item['id']} · {item.get('status') or 'Unknown'}"
                        f" · {item.get('zone') or 'No zone'}"
                    ),
                }
            )
    return references


TOOL_SCHEMAS = [
    {
        'type': 'function',
        'function': {
            'name': 'get_operations_summary',
            'description': (
                "Get today's aggregate operations summary: new, resolved, "
                'closed, unassigned, parts waiting, SLA risks, top zones, '
                'top issues, and engineer workload. Admin/Help Desk only.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {},
                'additionalProperties': False,
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_complaints',
            'description': (
                'Search complaints visible to the current user. Returns '
                'complaint IDs, status, zone, issues, age, and assigned '
                'engineer. Never returns caller PII.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': (
                            'Complaint ID, caller name, or phone. Engineers '
                            'can search by complaint ID only.'
                        ),
                    },
                    'statuses': {
                        'type': 'array',
                        'items': {'type': 'string', 'enum': STATUS_NAMES},
                    },
                    'zone': {
                        'type': 'string',
                        'description': 'Partial zone name.',
                    },
                    'engineer': {
                        'type': 'string',
                        'description': (
                            'Partial engineer name. Admin/Help Desk only.'
                        ),
                    },
                    'older_than_days': {'type': 'integer'},
                    'newer_than_days': {'type': 'integer'},
                    'created_within_hours': {
                        'type': 'integer',
                        'description': 'Only complaints created within this many hours.',
                    },
                    'ordering': {
                        'type': 'string',
                        'enum': ['newest', 'oldest'],
                    },
                    'limit': {
                        'type': 'integer',
                        'description': 'Maximum 20.',
                    },
                },
                'additionalProperties': False,
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_complaint',
            'description': (
                'Get non-PII detail for one visible complaint: creator, status, '
                'issues, age, current assignment, assignment history, job '
                'note, upload count, comment count, and the full status '
                'history with timestamps and the staff member who changed '
                'each status.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'complaint_id': {'type': 'integer'},
                },
                'required': ['complaint_id'],
                'additionalProperties': False,
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_engineer_workload',
            'description': (
                'Get active complaint counts by engineer. Admin/Help Desk only.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {},
                'additionalProperties': False,
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_sla_risks',
            'description': (
                'Get unresolved complaints older than seven days. Engineers '
                'see only their currently assigned complaints.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'limit': {'type': 'integer'},
                },
                'additionalProperties': False,
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_parts_queue',
            'description': (
                'Get complaints waiting for parts or with parts provided. '
                'Engineers see only their currently assigned complaints.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'limit': {'type': 'integer'},
                },
                'additionalProperties': False,
            },
        },
    },
]


ANALYTICS_TOOL_SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'run_analytics_query',
        'description': (
            'Run one read-only SELECT against the analytics views for a '
            'flexible ad-hoc analysis. Admin only. Use analytics_complaints, '
            'analytics_complaint_issues, analytics_status_events, and '
            'analytics_assignments. Never use base tables or caller PII.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'sql': {
                    'type': 'string',
                    'description': 'Exactly one read-only SELECT query.',
                },
            },
            'required': ['sql'],
            'additionalProperties': False,
        },
    },
}
