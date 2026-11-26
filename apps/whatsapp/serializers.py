from rest_framework import serializers


class WhatsAppSettingsSerializer(serializers.Serializer):
    use_whatsapp = serializers.BooleanField()


class WhatsAppMeUpdateSerializer(serializers.Serializer):
    whatsapp_opt_in = serializers.BooleanField()
