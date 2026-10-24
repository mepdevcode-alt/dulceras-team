from rest_framework.permissions import IsAuthenticated


class IsTeamMember(IsAuthenticated):
    """
    Panel admin (/api/admin/...): solo usuarios del negocio.
    Un cliente logueado tiene JWT válido pero no puede ver pedidos ni datos de otros clientes.
    """
    message = 'Esta cuenta no tiene acceso al panel de administración.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_team_member


class IsSuperadmin(IsAuthenticated):
    """Panel Sistema (/api/superadmin/...): registros técnicos, solo para el rol superadmin."""
    message = 'Solo el superadmin puede ver el panel Sistema.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_superadmin
