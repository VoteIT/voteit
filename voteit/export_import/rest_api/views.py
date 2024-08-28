from django.db import transaction
from pydantic import ValidationError as PydanticValidationError
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FileUploadParser
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.utils import pydantic_to_drf_validation_error
from voteit.meeting.models import Meeting
from voteit.export_import.exporter import Exporter
from voteit.export_import.importer import Importer
from voteit.export_import.rest_api.renderers import YAMLRenderer
from voteit.export_import.rest_api.serializers import ImportFileSerializer
from voteit.export_import.rest_api.serializers import ExportFileSerializer


@router.register("meeting-data", basename="meeting-data")
class MeetingDataViewSet(AutoPermissionViewSetMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Meeting.objects.all()
    serializer_class = ImportFileSerializer
    parser_classes = (MultiPartParser, FileUploadParser)

    @property
    def permission_type_map(self):
        return dict(
            yaml="moderate",
            json="moderate",
            preview="moderate",
            **super().permission_type_map,
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
            data=importer.data.dict(exclude_unset=True, exclude={"meta"}),
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
        renderer_classes=[JSONRenderer],
        parser_classes=[JSONParser],
    )
    def json(self, request, *args, **kwargs):
        return self._run_export(request, "json")

    @action(
        methods=["GET"],
        detail=True,
        renderer_classes=[YAMLRenderer],
    )
    def yaml(self, request, *args, **kwargs):
        return self._run_export(request, "yaml")

    def _run_export(self, request, file_suffix):
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
        return Response(
            exporter.data.dict(exclude_none=True),
            headers={
                f"Content-Disposition": f'attachment; filename="meeting_{instance.pk}_export.{file_suffix}"'
            },
        )
