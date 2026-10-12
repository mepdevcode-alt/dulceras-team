from rest_framework.permissions import IsAuthenticated


class IsTeamMember(IsAuthenticated):
    """
    Panel admin (/api/admin/...): solo usuarios del negocio o de la plataforma.
    Un cliente logueado tiene JWT válido pero no puede ver pedidos ni datos de otros clientes.
    """
    message = 'Esta cuenta no tiene acceso al panel de administración.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_team_member
