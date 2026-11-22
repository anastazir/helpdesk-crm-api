from rest_framework import serializers


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
