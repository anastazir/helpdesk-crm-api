from datetime import date, datetime, time as datetime_time, timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.permissions import IsAdmin
from core.responses import error_response, success_response

from .models import AIRequestLog
from .serializers import (
    AIRequestLogDetailSerializer,
    AIRequestLogListSerializer,
)
from .services import IST


def _parse_date(value, field):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{field} must be YYYY-MM-DD.')


def _money(value):
    if value is None:
        return 0.0
    return float(value)


class AIRequestLogListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        queryset = AIRequestLog.objects.select_related('user')
        feature = request.query_params.get('feature')
        log_status = request.query_params.get('status')
        search = (request.query_params.get('search') or '').strip()
        user_id = request.query_params.get('user_id')

        features = {choice[0] for choice in AIRequestLog.FEATURE_CHOICES}
        statuses = {choice[0] for choice in AIRequestLog.STATUS_CHOICES}
        if feature:
            if feature not in features:
                return error_response('Unknown AI feature filter.')
            queryset = queryset.filter(feature=feature)
        if log_status:
            if log_status not in statuses:
                return error_response('Unknown AI log status filter.')
            queryset = queryset.filter(status=log_status)
        if user_id:
            try:
                queryset = queryset.filter(user_id=int(user_id))
            except (TypeError, ValueError):
                return error_response('user_id must be an integer.')
        if search:
            queryset = queryset.filter(
                Q(user__full_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(request_text__icontains=search)
                | Q(response_text__icontains=search)
                | Q(error_message__icontains=search)
            )
        try:
            date_from = _parse_date(request.query_params.get('date_from'), 'date_from')
            date_to = _parse_date(request.query_params.get('date_to'), 'date_to')
        except ValueError as exc:
            return error_response(str(exc))
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        try:
            page_number = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except (TypeError, ValueError):
            return error_response('Invalid page parameters.')

        paginator = Paginator(queryset, page_size)
        page = paginator.get_page(page_number)
        results = AIRequestLogListSerializer(page.object_list, many=True).data
        return success_response(
            {
                'results': results,
                'count': paginator.count,
                'page': page.number,
                'page_size': page_size,
                'total_pages': paginator.num_pages,
            }
        )


class AIRequestLogDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, log_id):
        try:
            log = AIRequestLog.objects.select_related('user').get(pk=log_id)
        except AIRequestLog.DoesNotExist:
            return error_response(
                'AI log entry not found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return success_response(AIRequestLogDetailSerializer(log).data)


class AIRequestLogSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        now = timezone.now().astimezone(IST)
        today_start = datetime.combine(
            now.date(),
            datetime_time.min,
            tzinfo=IST,
        )
        queryset = AIRequestLog.objects.all()
        today = queryset.filter(created_at__gte=today_start)
        features = list(
            queryset.values('feature')
            .annotate(
                requests=Count('id'),
                total_tokens=Sum('total_tokens'),
                cost_inr=Sum('cost_inr'),
            )
            .order_by('-requests')
        )
        totals = queryset.aggregate(
            requests=Count('id'),
            total_tokens=Sum('total_tokens'),
            cost_inr=Sum('cost_inr'),
        )
        today_totals = today.aggregate(
            requests=Count('id'),
            cost_inr=Sum('cost_inr'),
        )
        errors = queryset.filter(status='error').count()
        return success_response(
            {
                'total_requests': totals['requests'] or 0,
                'total_tokens': totals['total_tokens'] or 0,
                'total_cost_inr': _money(totals['cost_inr']),
                'today_requests': today_totals['requests'] or 0,
                'today_cost_inr': _money(today_totals['cost_inr']),
                'errors': errors,
                'features': [
                    {
                        'feature': row['feature'],
                        'requests': row['requests'],
                        'total_tokens': row['total_tokens'] or 0,
                        'cost_inr': _money(row['cost_inr']),
                    }
                    for row in features
                ],
                'as_of': now.isoformat(),
            }
        )
