from rest_framework import exceptions
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['tenant_id'] = user.tenant_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Este endpoint es el login del panel admin; los clientes entran por /cuenta/login/
        if not self.user.is_team_member:
            raise exceptions.PermissionDenied(
                'Esta cuenta es de cliente. Ingresá desde /cuenta/login/.', code='customer_account',
            )
        return data
