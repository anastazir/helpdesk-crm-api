import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.complaints.models import Complaint, IssueType
from core.responses import error_response, success_response

from .serializers import (
    ChatRequestSerializer,
    CopilotRequestSerializer,
    EngineerPlanRequestSerializer,
    TriageRequestSerializer,
)
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
            logger.info(
                '[AI COPILOT] user=%s complaint=%s task=%s cost=%s',
                request.user.id,
                complaint.id,
                data['task'],
                (result.get('usage') or {}).get('cost'),
            )
            return success_response(result)
        except Exception as exc:
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
            logger.info(
                '[AI PLAN] user=%s cost=%s tokens=%s',
                request.user.id,
                (result.get('usage') or {}).get('cost'),
                (result.get('usage') or {}).get('total_tokens'),
            )
            return success_response(result)
        except Exception as exc:
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
            logger.info(
                '[AI TRIAGE] user=%s suggestions=%s urgency=%s cost=%s',
                request.user.id,
                len(result['suggested_issues']),
                result.get('urgency'),
                (result.get('usage') or {}).get('cost'),
            )
            return success_response(result)
        except Exception as exc:
            return _ai_failure_response(exc)
