from voteit.core.rest_api import router

from .views import DiscussionPostViewSet

router.register('discussion_posts', DiscussionPostViewSet)
