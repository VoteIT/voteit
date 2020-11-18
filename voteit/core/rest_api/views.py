from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from rest_framework import permissions
from rest_framework.authtoken.models import Token
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import GenericViewSet



class DevLogin(GenericViewSet, CreateModelMixin):
    """ DANGER! Not for production use!
        This will get or create an admin user, then get och create a valid API auth token.
    """
    permission_classes = [permissions.AllowAny]
    model = Token
    queryset = Token.objects.all()
    serializer_class = Serializer

    def create(self, request, *args, **kwargs):
        User: AbstractUser = get_user_model()
        try:
            admin_user = User.objects.get(username='admin')
        except User.DoesNotExist:
            admin_user = User.objects.create_user('admin', None, 'admin', is_superuser=True)
        token, created = Token.objects.get_or_create(user=admin_user)
        return Response({
            'key': token.key
        })
