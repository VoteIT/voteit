from voteit.core.rest_api import router
from voteit.proposal.rest_api.views import ProposalViewSet
from voteit.proposal.rest_api.views import TextDocumentViewSet

router.register("proposals", ProposalViewSet, basename="proposal")
router.register("text-documents", TextDocumentViewSet, basename="text-document")
