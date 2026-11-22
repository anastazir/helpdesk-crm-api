from rest_framework import serializers

from apps.exports.serializers import ExportFiltersSerializer


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=['user', 'assistant'])
    content = serializers.CharField(max_length=2000)


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)
    history = ChatMessageSerializer(many=True, required=False, default=list)
    language = serializers.ChoiceField(
        choices=['en', 'hi'],
        required=False,
        default='en',
    )


class CopilotRequestSerializer(serializers.Serializer):
    complaint_id = serializers.IntegerField()
    task = serializers.ChoiceField(
        choices=['summary', 'next_action', 'draft_comment']
    )
    language = serializers.ChoiceField(
        choices=['en', 'hi'],
        required=False,
        default='en',
    )
    instruction = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default='',
    )


class EngineerPlanRequestSerializer(serializers.Serializer):
    language = serializers.ChoiceField(
        choices=['en', 'hi'],
        required=False,
        default='en',
    )


class TriageRequestSerializer(serializers.Serializer):
    issue_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        max_length=10,
        default=list,
    )
    others_description = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        default='',
    )
    department = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default='',
    )
    designation = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default='',
    )
    language = serializers.ChoiceField(
        choices=['en', 'hi'],
        required=False,
        default='en',
    )

class AIRequestLogListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_name = serializers.CharField(source='user.full_name', allow_null=True)
    user_email = serializers.EmailField(source='user.email', allow_null=True)
    feature = serializers.CharField()
    status = serializers.CharField()
    model = serializers.CharField()
    provider = serializers.CharField()
    prompt_tokens = serializers.IntegerField()
    completion_tokens = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    cost_usd = serializers.DecimalField(max_digits=14, decimal_places=8, allow_null=True)
    cost_inr = serializers.DecimalField(max_digits=14, decimal_places=4, allow_null=True)
    latency_ms = serializers.IntegerField()
    tools_used = serializers.JSONField()
    error_message = serializers.CharField()
    created_at = serializers.DateTimeField()
    request_preview = serializers.SerializerMethodField()
    response_preview = serializers.SerializerMethodField()

    def get_request_preview(self, obj):
        return (obj.request_text or '')[:240]

    def get_response_preview(self, obj):
        return (obj.response_text or '')[:240]


class AIRequestLogDetailSerializer(AIRequestLogListSerializer):
    request_text = serializers.CharField()
    response_text = serializers.CharField()
    metadata = serializers.JSONField()


class ExportSummaryRequestSerializer(serializers.Serializer):
    filters = ExportFiltersSerializer(required=False)
    deduplicate = serializers.BooleanField(required=False, default=False)
    language = serializers.ChoiceField(
        choices=['en', 'hi'],
        required=False,
        default='en',
    )


class ComplaintAutofillRequestSerializer(serializers.Serializer):
    transcript = serializers.CharField(max_length=5000)
    language = serializers.ChoiceField(
        choices=['en', 'hi'],
        required=False,
        default='en',
    )


class AnalyticsRequestSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=500)
    language = serializers.ChoiceField(
        choices=['en', 'hi'],
        required=False,
        default='en',
    )
