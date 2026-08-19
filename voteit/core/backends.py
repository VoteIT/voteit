from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class PrefetchedModelBackend(ModelBackend):
    def get_user(self, user_id):
        try:
            user = User._default_manager.select_related("organisation").get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None

    async def aget_user(self, user_id):
        try:
            user = await User._default_manager.select_related("organisation").aget(
                pk=user_id
            )
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
