import logging
import time
from datetime import date, datetime
from decimal import Decimal

import sqlglot
from django.conf import settings
from django.db import connection
from sqlglot import exp

try:
    import psycopg
except ImportError:
    psycopg = None

logger = logging.getLogger('apps.assistant')

ALLOWED_VIEWS = {
    'analytics_complaints',
    'analytics_complaint_issues',
    'analytics_status_events',
    'analytics_assignments',
}

FORBIDDEN_NODE_NAMES = [
    'Insert',
    'Update',
    'Delete',
    'Merge',
    'Create',
    'Drop',
    'Alter',
    'TruncateTable',
    'Command',
    'Copy',
    'Set',
    'Grant',
    'Revoke',
    'Lock',
    'Into',
    'Transaction',
    'Commit',
    'Rollback',
]
FORBIDDEN_NODES = tuple(
    node
    for node in (getattr(exp, name, None) for name in FORBIDDEN_NODE_NAMES)
    if node is not None
)

ALLOWED_FUNCTIONS = {
    'ABS',
    'AND',
    'BETWEEN',
    'CASE',
    'ILIKE',
    'IS',
    'LIKE',
    'NOT',
    'OR',
    'XOR',
    'AGE',
    'ARRAY_AGG',
    'AVG',
    'CAST',
    'CEIL',
    'CEILING',
    'COALESCE',
    'CONCAT',
    'COUNT',
    'CURRENT_DATE',
    'CURRENT_TIMESTAMP',
    'DATE',
    'DATE_PART',
    'DATE_TRUNC',
    'DATEADD',
    'DATEDIFF',
    'DATETIME',
    'DENSE_RANK',
    'EXTRACT',
    'FIRST_VALUE',
    'FLOOR',
    'GREATEST',
    'GROUP_CONCAT',
    'IF',
    'IFNULL',
    'JULIANDAY',
    'LAG',
    'LAST_VALUE',
    'LEAD',
    'LEAST',
    'LENGTH',
    'LOWER',
    'MAX',
    'MIN',
    'MOD',
    'NOW',
    'NULLIF',
    'POWER',
    'RANK',
    'REPLACE',
    'ROUND',
    'ROW_NUMBER',
    'SQRT',
    'STDDEV',
    'STRFTIME',
    'STRING_AGG',
    'SUBSTR',
    'SUBSTRING',
    'SUM',
    'TIME_TO_STR',
    'TO_CHAR',
    'TRIM',
    'TS_OR_DS_TO_TIMESTAMP',
    'UPPER',
    'VARIANCE',
}


class AnalyticsError(Exception):
    pass


class AnalyticsValidationError(AnalyticsError):
    pass


class AnalyticsConfigurationError(AnalyticsError):
    pass


class AnalyticsExecutionError(AnalyticsError):
    pass


def analytics_dialect():
    if settings.ANALYTICS_DATABASE_URL:
        return 'postgres'
    return 'postgres' if connection.vendor == 'postgres' else 'sqlite'


def analytics_schema_text():
    return """
Available analytics views (read-only; no caller PII):
- analytics_complaints(complaint_id, created_at, status, zone, department, assigned_engineer_id, assigned_engineer, created_by_id, created_by_name, created_by_role)
- analytics_complaint_issues(complaint_id, issue_id, issue)
- analytics_status_events(id, complaint_id, previous_status, new_status, changed_at, changed_by_id, changed_by_name, changed_by_role)
- analytics_assignments(id, complaint_id, engineer_id, engineer, assigned_at, unassigned_at, assigned_by_id, assigned_by_name, assigned_by_role, unassigned_by_id, unassigned_by_name, unassigned_by_role)

Only use these views. Do not use base application tables. Staff names and roles
are available in the *_name and *_role columns. Caller PII is intentionally absent.
Complaint statuses: open, assigned, in_progress, parts_requested, parts_provided, resolved, closed.
The reporting timezone is Asia/Kolkata. Current server time will be supplied in the prompt.
""".strip()


def _function_name(node):
    if isinstance(node, exp.Anonymous):
        return str(node.name or '').upper()
    return str(node.sql_name() or '').upper()


def validate_analytics_sql(sql, max_rows=None):
    if not isinstance(sql, str) or not sql.strip():
        raise AnalyticsValidationError('SQL is empty.')
    if len(sql) > 20000:
        raise AnalyticsValidationError('SQL is too large.')

    dialect = analytics_dialect()
    try:
        statements = [
            statement
            for statement in sqlglot.parse(sql, read=dialect)
            if statement is not None
        ]
    except Exception as exc:
        raise AnalyticsValidationError(
            'The SQL could not be parsed.'
        ) from exc

    if len(statements) != 1:
        raise AnalyticsValidationError('Exactly one SQL statement is required.')

    root = statements[0]
    allowed_roots = (exp.Select, exp.Union, exp.Intersect, exp.Except)
    if not isinstance(root, allowed_roots):
        raise AnalyticsValidationError('Only SELECT queries are allowed.')

    cte_names = {
        cte.alias_or_name.lower()
        for cte in root.find_all(exp.CTE)
        if cte.alias_or_name
    }
    for node in root.walk():
        if FORBIDDEN_NODES and isinstance(node, FORBIDDEN_NODES):
            raise AnalyticsValidationError(
                'The SQL contains a prohibited statement type.'
            )
        if isinstance(node, exp.Table):
            table_name = (node.name or '').lower()
            schema_name = (node.db or '').lower()
            if table_name not in ALLOWED_VIEWS and table_name not in cte_names:
                raise AnalyticsValidationError(
                    f'Table or view is not allowed: {table_name}.'
                )
            if schema_name and schema_name not in ('main', 'public'):
                raise AnalyticsValidationError(
                    f'Schema access is not allowed: {schema_name}.'
                )
        if isinstance(node, exp.Func):
            function_name = _function_name(node)
            if function_name not in ALLOWED_FUNCTIONS:
                raise AnalyticsValidationError(
                    f'Function is not allowed: {function_name}.'
                )

    normalized = root.sql(dialect=dialect)
    limit = max_rows or settings.ANALYTICS_MAX_ROWS
    wrapped = (
        f'SELECT * FROM ({normalized}) AS analytics_q '
        f'LIMIT {int(limit) + 1}'
    )
    return {
        'sql': normalized,
        'wrapped_sql': wrapped,
        'max_rows': int(limit),
        'dialect': dialect,
    }


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return '<binary>'
    return value


def _rows_as_dicts(columns, records):
    rows = []
    for record in records:
        rows.append(
            {
                column: _json_safe(value)
                for column, value in zip(columns, record)
            }
        )
    return rows


def execute_analytics_sql(sql, max_rows=None):
    validated = validate_analytics_sql(sql, max_rows=max_rows)
    started = time.monotonic()
    columns = []
    records = []

    try:
        if settings.ANALYTICS_DATABASE_URL:
            if psycopg is None:
                raise AnalyticsConfigurationError(
                    'The PostgreSQL driver is not installed.'
                )
            conn = psycopg.connect(
                settings.ANALYTICS_DATABASE_URL,
                connect_timeout=5,
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute('BEGIN READ ONLY')
                    cursor.execute(
                        f'SET LOCAL statement_timeout = '
                        f'{int(settings.ANALYTICS_QUERY_TIMEOUT_MS)}'
                    )
                    cursor.execute(validated['wrapped_sql'])
                    columns = [desc.name for desc in cursor.description]
                    records = cursor.fetchmany(validated['max_rows'] + 1)
                    conn.rollback()
            finally:
                conn.close()
        else:
            if connection.vendor != 'sqlite':
                raise AnalyticsConfigurationError(
                    'ANALYTICS_DATABASE_URL must point to a read-only '
                    'PostgreSQL role.'
                )
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA query_only = ON')
                try:
                    cursor.execute(validated['wrapped_sql'])
                    columns = [desc[0] for desc in cursor.description]
                    records = cursor.fetchmany(validated['max_rows'] + 1)
                finally:
                    cursor.execute('PRAGMA query_only = OFF')
    except AnalyticsError:
        raise
    except Exception as exc:
        logger.warning('[ANALYTICS SQL] Execution failed: %s', exc)
        raise AnalyticsExecutionError(
            f'Analytics query failed: {str(exc)[:300]}'
        ) from exc

    truncated = len(records) > validated['max_rows']
    if truncated:
        records = records[: validated['max_rows']]

    return {
        'sql': validated['sql'],
        'columns': columns,
        'rows': _rows_as_dicts(columns, records),
        'row_count': len(records),
        'truncated': truncated,
        'dialect': validated['dialect'],
        'duration_ms': int((time.monotonic() - started) * 1000),
    }
