from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from voteit.bug_reports.models import BugReport
from voteit.bug_reports.rest_api.serializers import BugReportSerializer
from voteit.core.rest_api import router


@router.register("bug-reports")
class BugReportView(ModelViewSet):
    model = BugReport
    queryset = BugReport.objects.all()
    serializer_class = BugReportSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return BugReport.objects.filter(user=self.request.user)
