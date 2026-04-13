import yaml
from django.db import transaction
from django.http import HttpResponse
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FileUploadParser
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.core.rest_api.utils import pydantic_to_drf_validation_error
from voteit.export_import.utils import sign_payload
from voteit.export_import.exporter import Exporter
from voteit.export_import.importer import Importer
from voteit.export_import.rest_api.serializers import ImportFileSerializer
from voteit.export_import.rest_api.serializers import ExportFileSerializer
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR


@router.register("meeting-data", basename="meeting-data")
class MeetingDataViewSet(VerboseAutoPermissionViewSetMixin, viewsets.GenericViewSet):
    serializer_class = ImportFileSerializer
    parser_classes = (MultiPartParser, FileUploadParser)
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "preview": None,
        "yaml": None,
    }

    def get_queryset(self):
        return Meeting.objects.filter(
            roles__user=self.request.user, roles__assigned__contains=ROLE_MODERATOR
        )

    def list(self, request, *args, **kwargs):
        return Response(data=[])

    @action(
        methods=["POST"],
        detail=True,
    )
    def preview(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={"meeting": instance, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            importer = Importer(
                instance, **{k: v for k, v in serializer.data.items() if k != "file"}
            )
            importer.from_stream(request.data["file"])
        except PydanticValidationError as exc:
            raise pydantic_to_drf_validation_error(exc)
        return Response(
            data=importer.data.dict(exclude_unset=True, exclude={"meta", "sign"}),
            status=status.HTTP_200_OK,
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={"meeting": instance, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        # Dispatch job?
        try:
            importer = Importer(
                instance, **{k: v for k, v in serializer.data.items() if k != "file"}
            )
            importer.from_stream(request.data["file"])
        except PydanticValidationError as exc:
            raise pydantic_to_drf_validation_error(exc)
        with transaction.atomic(durable=True):
            importer.run()
        return Response(
            data=importer.stats().dict(),
            status=status.HTTP_200_OK,
        )

    @action(
        methods=["GET"],
        detail=True,
    )
    def yaml(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ExportFileSerializer(
            data=request.query_params,
        )
        serializer.is_valid(raise_exception=True)
        exporter = Exporter(instance, **serializer.data)
        try:
            exporter()
        except PydanticValidationError as exc:
            raise pydantic_to_drf_validation_error(exc)
        payload = yaml.dump(exporter.data.dict(exclude_none=True))
        signed_payload = f"sign: {sign_payload(payload)}\n" + payload
        return HttpResponse(
            signed_payload,
            content_type="application/yaml",
            headers={
                "Content-Disposition": f'attachment; filename="meeting_{instance.pk}_export.yaml"'
            },
        )
