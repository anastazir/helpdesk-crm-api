import json
import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.complaints.models import Complaint, IssueType
from apps.exports.builder import get_matching_complaints, deduplicate_complaints
from apps.zones.models import Zone
from core.responses import error_response, success_response

from .serializers import (
    ChatRequestSerializer,
    CopilotRequestSerializer,
    EngineerPlanRequestSerializer,
    TriageRequestSerializer,
    ExportSummaryRequestSerializer,
    ComplaintAutofillRequestSerializer,
    AnalyticsRequestSerializer,
)
from .audit import log_ai_request
from .services import (
    BriefingConfigurationError,
    BriefingInputError,
    BriefingUpstreamError,
    build_briefing_context,
    chat_with_tools,
    generate_briefing,
    generate_complaint_copilot,
    generate_engineer_plan,
    generate_triage,
    generate_export_summary,
    generate_complaint_autofill,
    generate_analytics_plan,
    generate_analytics_answer,
    _usage_from,
)
from .analytics import (
    AnalyticsConfigurationError,
    AnalyticsError,
    AnalyticsExecutionError,
    AnalyticsValidationError,
    execute_analytics_sql,
)
from .tools import (
    build_complaint_context,
    can_view_complaint,
    is_assigned_to,
)

logger = logging.getLogger('apps.assistant')


def _role_forbidden(message):
    return error_response(message, status_code=status.HTTP_403_FORBIDDEN)


def _ai_failure_response(exc):
    if isinstance(exc, BriefingConfigurationError):
        return error_response(
            'AI is not configured on this server.',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, BriefingInputError):
        return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, BriefingUpstreamError):
        logger.warning('[AI] Upstream failure: %s', exc)
        return error_response(
            str(exc),
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    logger.exception('[AI] Unexpected failure')
    return error_response(
        'The AI request could not be completed. Please try again.',
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class DailyBriefingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ('admin', 'helpdesk'):
            return _role_forbidden(
                'Only Admin and Help Desk users can generate the AI briefing.'
            )

        if not settings.AI_BRIEFING_ENABLED:
            return error_response(
                'AI briefing is disabled.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        lock_key = f'ai-briefing-lock:{request.user.id}'
        if not cache.add(lock_key, True, timeout=20):
            return error_response(
                'A briefing is already being generated. Please wait a moment.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            context = build_briefing_context()
            result = generate_briefing(context)
            log_ai_request(
                user=request.user,
                feature='briefing',
                status='success',
                request_text="Today's daily briefing",
                response_text=result.get('briefing', ''),
                result=result,
            )
            logger.info(
                '[AI BRIEFING] user=%s cost=%s tokens=%s latency_ms=%s',
                request.user.id,
                (result.get('usage') or {}).get('cost'),
                (result.get('usage') or {}).get('total_tokens'),
                result.get('latency_ms'),
            )
            return success_response(
                result,
                message='Daily briefing generated.',
            )
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='briefing',
                status='error',
                request_text="Today's daily briefing",
                error_message=str(exc),
            )
            return _ai_failure_response(exc)
        finally:
            cache.delete(lock_key)


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the chat message.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        lock_key = f'ai-chat-lock:{request.user.id}'
        if not cache.add(lock_key, True, timeout=20):
            return error_response(
                'The assistant is already answering. Please wait a moment.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            result = chat_with_tools(
                request.user,
                serializer.validated_data['message'],
                serializer.validated_data.get('history', []),
                serializer.validated_data.get('language', 'en'),
            )
            log_ai_request(
                user=request.user,
                feature='chat',
                status='success',
                request_text=serializer.validated_data['message'],
                response_text=result.get('reply', ''),
                result=result,
                metadata={
                    'history': serializer.validated_data.get('history', []),
                    'tools_used': result.get('tools_used', []),
                    'tool_events': result.get('tool_events', []),
                    'references': result.get('references', []),
                },
            )
            logger.info(
                '[AI CHAT] user=%s tools=%s cost=%s tokens=%s latency_ms=%s',
                request.user.id,
                ','.join(result.get('tools_used') or []) or 'none',
                (result.get('usage') or {}).get('cost'),
                (result.get('usage') or {}).get('total_tokens'),
                result.get('latency_ms'),
            )
            return success_response(result)
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='chat',
                status='error',
                request_text=serializer.validated_data.get('message', ''),
                error_message=str(exc),
            )
            return _ai_failure_response(exc)
        finally:
            cache.delete(lock_key)


class ComplaintCopilotView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CopilotRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the complaint copilot request.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        try:
            complaint = Complaint.objects.select_related('zone').get(
                pk=data['complaint_id']
            )
        except Complaint.DoesNotExist:
            return error_response(
                'Complaint not found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if not can_view_complaint(request.user, complaint):
            return _role_forbidden('You do not have access to this complaint.')

        if data['task'] == 'draft_comment':
            can_draft = (
                request.user.role in ('admin', 'helpdesk')
                or is_assigned_to(request.user, complaint)
            )
            if not can_draft:
                return _role_forbidden(
                    'You cannot draft a comment for this complaint.'
                )
            if complaint.status == 'closed':
                return error_response(
                    'Closed complaints cannot receive new comments.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        try:
            result = generate_complaint_copilot(
                build_complaint_context(complaint),
                data['task'],
                data.get('language', 'en'),
                data.get('instruction', ''),
            )
            log_ai_request(
                user=request.user,
                feature='complaint_copilot',
                status='success',
                request_text=(
                    f"Complaint {complaint.id}: {data['task']} "
                    f"{data.get('instruction', '')}"
                ).strip(),
                response_text=result.get('text', ''),
                result=result,
                metadata={'complaint_id': complaint.id, 'task': data['task']},
            )
            logger.info(
                '[AI COPILOT] user=%s complaint=%s task=%s cost=%s',
                request.user.id,
                complaint.id,
                data['task'],
                (result.get('usage') or {}).get('cost'),
            )
            return success_response(result)
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='complaint_copilot',
                status='error',
                request_text=f"Complaint {data['complaint_id']}: {data['task']}",
                error_message=str(exc),
            )
            return _ai_failure_response(exc)


class EngineerPlanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'engineer':
            return _role_forbidden('The daily plan is available to engineers.')

        serializer = EngineerPlanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the daily plan request.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        complaints = (
            Complaint.objects.select_related('zone', 'job_note')
            .prefetch_related('issues', 'uploads', 'status_history', 'comments')
            .filter(
                assignments__engineer=request.user,
                assignments__unassigned_at__isnull=True,
            )
            .exclude(status='closed')
            .distinct()
            .order_by('created_at')[:30]
        )
        try:
            result = generate_engineer_plan(
                [build_complaint_context(complaint) for complaint in complaints],
                serializer.validated_data.get('language', 'en'),
            )
            log_ai_request(
                user=request.user,
                feature='engineer_plan',
                status='success',
                request_text='Engineer day plan',
                response_text=result.get('text', ''),
                result=result,
            )
            logger.info(
                '[AI PLAN] user=%s cost=%s tokens=%s',
                request.user.id,
                (result.get('usage') or {}).get('cost'),
                (result.get('usage') or {}).get('total_tokens'),
            )
            return success_response(result)
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='engineer_plan',
                status='error',
                request_text='Engineer day plan',
                error_message=str(exc),
            )
            return _ai_failure_response(exc)


class TriageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ('admin', 'helpdesk'):
            return _role_forbidden(
                'Only Admin and Help Desk users can use AI triage.'
            )

        serializer = TriageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the triage request.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        issues = list(IssueType.objects.filter(is_active=True).order_by('order'))
        issue_by_id = {issue.id: issue for issue in issues}
        selected_ids = data.get('issue_ids', [])
        if any(issue_id not in issue_by_id for issue_id in selected_ids):
            return error_response(
                'One or more selected issue types are not available.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        selected_issues = [
            issue_by_id[issue_id].name
            for issue_id in selected_ids
            if issue_id in issue_by_id
        ]
        description = (data.get('others_description') or '').strip()
        if not selected_issues and not description:
            return error_response(
                'Select an issue or describe the problem before using AI triage.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = generate_triage(
                [issue.name for issue in issues],
                selected_issues,
                description,
                data.get('department', ''),
                data.get('designation', ''),
                data.get('language', 'en'),
            )
            name_to_issue = {issue.name: issue for issue in issues}
            result['suggested_issues'] = [
                {
                    'id': name_to_issue[name].id,
                    'name': name,
                }
                for name in result.get('suggested_issues', [])
                if name in name_to_issue
            ]
            log_ai_request(
                user=request.user,
                feature='triage',
                status='success',
                request_text=description or ', '.join(selected_issues),
                response_text=json.dumps(result, ensure_ascii=False),
                result=result,
                metadata={
                    'selected_issues': selected_issues,
                    'urgency': result.get('urgency'),
                },
            )
            logger.info(
                '[AI TRIAGE] user=%s suggestions=%s urgency=%s cost=%s',
                request.user.id,
                len(result['suggested_issues']),
                result.get('urgency'),
                (result.get('usage') or {}).get('cost'),
            )
            return success_response(result)
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='triage',
                status='error',
                request_text=description or ', '.join(selected_issues),
                error_message=str(exc),
            )
            return _ai_failure_response(exc)



class ExportSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'admin':
            return _role_forbidden('AI export summaries are available to admins only.')

        serializer = ExportSummaryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the export summary request.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        filters = data.get('filters') or {}
        all_matching = get_matching_complaints(filters=filters, deduplicate=False)
        matching = (
            deduplicate_complaints(all_matching)
            if data.get('deduplicate')
            else all_matching
        )
        status_counts = {}
        zone_counts = {}
        issue_counts = {}
        unresolved = []
        now = timezone.now()
        for complaint in matching:
            label = complaint.get_status_display()
            status_counts[label] = status_counts.get(label, 0) + 1
            zone_name = complaint.zone.name if complaint.zone else 'No zone'
            zone_counts[zone_name] = zone_counts.get(zone_name, 0) + 1
            for issue in complaint.issues.all():
                issue_counts[issue.name] = issue_counts.get(issue.name, 0) + 1
            if complaint.status != 'closed':
                unresolved.append(complaint)

        oldest = [
            {
                'id': complaint.id,
                'status': complaint.get_status_display(),
                'zone': complaint.zone.name if complaint.zone else None,
                'age_days': max(
                    0,
                    int((now - complaint.created_at).total_seconds() // 86400),
                ),
            }
            for complaint in sorted(unresolved, key=lambda item: item.created_at)[:5]
        ]
        context = {
            'total_matching': len(all_matching),
            'after_deduplication': len(matching),
            'deduplicated_count': len(all_matching) - len(matching),
            'status_counts': dict(
                sorted(status_counts.items(), key=lambda item: -item[1])
            ),
            'zone_counts': dict(
                sorted(zone_counts.items(), key=lambda item: -item[1])[:8]
            ),
            'issue_counts': dict(
                sorted(issue_counts.items(), key=lambda item: -item[1])[:8]
            ),
            'sla_risk_over_7_days': sum(
                1
                for complaint in unresolved
                if (now - complaint.created_at).days > 7
            ),
            'oldest_unresolved': oldest,
            'filters': {
                'date_from': filters.get('date_from'),
                'date_to': filters.get('date_to'),
            },
            'as_of': now.isoformat(),
        }

        try:
            result = generate_export_summary(
                context,
                data.get('language', 'en'),
            )
            log_ai_request(
                user=request.user,
                feature='export_summary',
                status='success',
                request_text='AI summary of the current export filters',
                response_text=result.get('text', ''),
                result=result,
                metadata={
                    'filters': {
                        key: (value.isoformat() if hasattr(value, 'isoformat') else value)
                        for key, value in (serializer.validated_data.get('filters') or {}).items()
                    },
                },
            )
            return success_response(result)
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='export_summary',
                status='error',
                request_text='AI summary of the current export filters',
                error_message=str(exc),
            )
            return _ai_failure_response(exc)


class ComplaintAutofillView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ('admin', 'helpdesk'):
            return _role_forbidden(
                'Only Admin and Help Desk users can use complaint autofill.'
            )

        serializer = ComplaintAutofillRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the autofill transcript.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        transcript = serializer.validated_data['transcript'].strip()
        if not transcript:
            return error_response(
                'Dictate or enter the complaint details first.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        issues = list(IssueType.objects.filter(is_active=True).order_by('order'))
        zones = list(Zone.objects.order_by('name'))
        try:
            result = generate_complaint_autofill(
                transcript,
                [issue.name for issue in issues],
                [zone.name for zone in zones],
                serializer.validated_data.get('language', 'en'),
            )
            fields = result.get('fields') or {}
            phone = re.sub(r'\D', '', str(fields.get('caller_phone') or ''))
            if not phone:
                digits = re.sub(r'\D', '', transcript)
                match = re.search(r'(?:91)?0?([6-9]\d{9})', digits)
                if match:
                    phone = match.group(1)
            if phone:
                phone = phone[-10:]
                fields['caller_phone'] = phone
            pincode = re.sub(r'\D', '', str(fields.get('pincode') or ''))
            fields['pincode'] = pincode[-6:] if len(pincode) >= 6 else None
            issue_by_name = {issue.name.lower(): issue for issue in issues}
            suggested_issues = []
            for name in fields.get('issue_names') or []:
                issue = issue_by_name.get(str(name).strip().lower())
                if issue and issue not in suggested_issues:
                    suggested_issues.append(issue)
            zone = None
            zone_name = fields.get('zone')
            if zone_name:
                zone = next(
                    (item for item in zones if item.name.lower() == str(zone_name).strip().lower()),
                    None,
                )
            result['suggested_issues'] = [
                {'id': issue.id, 'name': issue.name}
                for issue in suggested_issues
            ]
            result['suggested_issue_ids'] = [issue.id for issue in suggested_issues]
            result['zone_id'] = zone.id if zone else None
            result['zone_name'] = zone.name if zone else None
            result.pop('fields', None)
            result['fields'] = fields
            log_ai_request(
                user=request.user,
                feature='complaint_autofill',
                status='success',
                request_text=transcript,
                response_text=json.dumps(result, ensure_ascii=False),
                result=result,
                metadata={'suggested_issue_ids': result['suggested_issue_ids']},
            )
            return success_response(result)
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='complaint_autofill',
                status='error',
                request_text=transcript,
                error_message=str(exc),
            )
            return _ai_failure_response(exc)



def _merge_usage(total, usage):
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        total[key] = total.get(key, 0) + (usage.get(key) or 0)
    if usage.get('cost') is not None:
        total['cost'] = (total.get('cost') or 0) + usage['cost']


def _infer_analytics_chart(question, columns, rows):
    lower = question.lower()
    if any(
        phrase in lower
        for phrase in ('list ', 'show complaints', 'complaint ids', 'details', 'which complaints')
    ):
        return None
    if not any(
        phrase in lower
        for phrase in (' by ', 'compare', 'trend', 'over time', 'distribution', 'breakdown', 'this week', 'last ')
    ):
        return None
    numeric = [
        column
        for column in columns
        if any(isinstance(row.get(column), (int, float)) for row in rows)
    ]
    categorical = [
        column
        for column in columns
        if column not in numeric
        and len({str(row.get(column)) for row in rows}) <= 20
    ]
    if not numeric or not categorical:
        return None
    x_field = categorical[0]
    y_field = numeric[0]
    if any(term in lower for term in ('trend', 'over time', 'daily', 'hourly', 'week', 'month', 'date')):
        chart_type = 'line'
    elif any(term in lower for term in ('distribution', 'status')):
        chart_type = 'donut'
    else:
        chart_type = 'bar'
    return {
        'type': chart_type,
        'x': x_field,
        'y': y_field,
        'series': None,
    }


def _analytics_result_meta(usage, latency, data):
    cost = usage.get('cost')
    usage['cost_inr'] = (
        round(float(cost) * settings.USD_TO_INR_RATE, 4)
        if cost is not None
        else None
    )
    return {
        'generated_at': timezone.now().isoformat(),
        'model': (data or {}).get('model') or settings.OPENROUTER_MODEL,
        'provider': (data or {}).get('provider'),
        'usage': usage,
        'latency_ms': latency,
    }


class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'admin':
            return _role_forbidden('AI analytics is available to admins only.')
        if not settings.ANALYTICS_ENABLED:
            return error_response(
                'AI analytics is disabled.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = AnalyticsRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the analytics question.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )
        question = serializer.validated_data['question'].strip()
        language = serializer.validated_data.get('language', 'en')

        lock_key = f'ai-analytics-lock:{request.user.id}'
        if not cache.add(lock_key, True, timeout=30):
            return error_response(
                'An analysis is already running. Please wait.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        usage = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'cost': None,
        }
        latency_total = 0
        last_data = None
        previous_sql = None
        sql_error = None
        result = None
        plan = None
        try:
            for _ in range(2):
                plan, plan_data, plan_latency = generate_analytics_plan(
                    question,
                    language,
                    previous_sql=previous_sql,
                    sql_error=sql_error,
                )
                last_data = plan_data
                latency_total += plan_latency
                _merge_usage(usage, _usage_from(plan_data))
                try:
                    result = execute_analytics_sql(plan['sql'])
                    break
                except (AnalyticsValidationError, AnalyticsExecutionError) as exc:
                    previous_sql = plan.get('sql')
                    sql_error = str(exc)

            if result is None:
                log_ai_request(
                    user=request.user,
                    feature='analytics',
                    status='error',
                    request_text=question,
                    error_message=sql_error or 'Analytics query failed.',
                    metadata={'previous_sql': previous_sql},
                )
                return error_response(
                    'Could not produce a valid analytics query for that question.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            chart = plan.get('chart') or {}
            columns = result.get('columns') or []
            rows = result.get('rows') or []
            chart_type = chart.get('type') or 'table'
            response_type = plan.get('response_type') or 'table'
            x_field = chart.get('x')
            y_field = chart.get('y')
            series_field = chart.get('series')
            if series_field not in columns:
                series_field = None
            chart_is_valid = (
                response_type == 'chart'
                and chart_type in ('bar', 'line', 'area', 'donut', 'kpi')
                and y_field in columns
                and (chart_type == 'kpi' or x_field in columns)
                and any(
                    isinstance(row.get(y_field), (int, float))
                    for row in rows
                )
            )
            if not chart_is_valid:
                inferred = _infer_analytics_chart(question, columns, rows)
                if inferred:
                    chart_type = inferred['type']
                    x_field = inferred['x']
                    y_field = inferred['y']
                    series_field = inferred['series']
                    response_type = 'chart'
                    chart_is_valid = True

            if result.get('row_count', 0) > 500 or not chart_is_valid:
                chart_type = 'table'
                response_type = 'table'
                x_field = None
                y_field = None
                series_field = None

            answer = ''
            try:
                answer, answer_data, answer_latency = generate_analytics_answer(
                    question,
                    plan,
                    result,
                    language,
                )
                last_data = answer_data
                latency_total += answer_latency
                _merge_usage(usage, _usage_from(answer_data))
            except Exception as exc:
                logger.warning('[AI ANALYTICS] Answer generation failed: %s', exc)

            response_data = {
                'question': question,
                'sql': result['sql'],
                'columns': columns,
                'rows': rows,
                'row_count': result['row_count'],
                'truncated': result['truncated'],
                'dialect': result['dialect'],
                'title': plan.get('title') or 'AI analysis',
                'response_type': response_type,
                'chart': {
                    'type': chart_type,
                    'x': x_field if chart_type != 'table' else None,
                    'y': y_field if chart_type != 'table' else None,
                    'series': series_field if chart_type != 'table' else None,
                },
                'explanation': plan.get('explanation') or '',
                'answer': answer or plan.get('explanation') or '',
                **_analytics_result_meta(usage, latency_total, last_data),
            }
            log_ai_request(
                user=request.user,
                feature='analytics',
                status='success',
                request_text=question,
                response_text=response_data['answer'],
                result=response_data,
                metadata={
                    'sql': result['sql'],
                    'chart': response_data['chart'],
                    'row_count': result['row_count'],
                    'truncated': result['truncated'],
                },
            )
            logger.info(
                '[AI ANALYTICS] user=%s rows=%s cost=%s tokens=%s',
                request.user.id,
                result['row_count'],
                usage.get('cost'),
                usage.get('total_tokens'),
            )
            return success_response(response_data)
        except BriefingConfigurationError as exc:
            log_ai_request(
                user=request.user,
                feature='analytics',
                status='error',
                request_text=question,
                error_message=str(exc),
            )
            return _ai_failure_response(exc)
        except AnalyticsConfigurationError as exc:
            log_ai_request(
                user=request.user,
                feature='analytics',
                status='error',
                request_text=question,
                error_message=str(exc),
            )
            return error_response(
                str(exc),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AnalyticsError as exc:
            log_ai_request(
                user=request.user,
                feature='analytics',
                status='error',
                request_text=question,
                error_message=str(exc),
            )
            return error_response(
                str(exc),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:
            log_ai_request(
                user=request.user,
                feature='analytics',
                status='error',
                request_text=question,
                error_message=str(exc),
            )
            return _ai_failure_response(exc)
        finally:
            cache.delete(lock_key)
