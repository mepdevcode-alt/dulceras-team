from django.conf import settings
from django.db import models
from core.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='audit_logs'
    )
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50)
    changes = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'registros_auditoria'
        ordering = ['-created_at']
        verbose_name = 'Log de auditoría'
        verbose_name_plural = 'Logs de auditoría'

    def __str__(self):
        return f"{self.action} {self.model_name}#{self.object_id} por {self.user}"
