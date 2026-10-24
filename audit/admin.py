from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'object_id', 'user', 'ip_address', 'created_at')
    list_filter = ('action', 'model_name')
    search_fields = ('model_name', 'object_id', 'user__username')
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'changes', 'ip_address', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
