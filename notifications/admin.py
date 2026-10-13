from django.contrib import admin
from .models import Notification, WhatsAppLog


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'type', 'is_read', 'created_at')
    list_filter = ('type', 'is_read')
    search_fields = ('title', 'message', 'recipient__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WhatsAppLog)
class WhatsAppLogAdmin(admin.ModelAdmin):
    list_display = ('phone', 'sent', 'sent_at', 'created_at')
    list_filter = ('sent',)
    search_fields = ('phone',)
    readonly_fields = ('created_at', 'updated_at')
