from voteit.core.rest_api import router

from .views import ProposalViewSet

router.register('proposals', ProposalViewSet)
