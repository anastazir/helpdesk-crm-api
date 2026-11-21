from django.contrib import admin

from .models import EngineerZoneAssignment, Zone


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(EngineerZoneAssignment)
class EngineerZoneAssignmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'engineer', 'zone', 'action', 'changed_at', 'changed_by']
    list_filter = ['action']
