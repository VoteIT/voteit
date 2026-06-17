import yaml
from django.db import transaction
from django.http import HttpResponse
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FileUploadParser
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from yaml.reader import ReaderError

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.core.rest_api.utils import pydantic_to_drf_validation_error
from voteit.export_import.exceptions import ImportFileError
from voteit.export_import.exceptions import SignatureVerificationFailed
from voteit.export_import.utils import MAX_IMPORT_BYTES
from voteit.export_import.utils import MAX_UNSIGNED_IMPORT_BYTES
from voteit.export_import.utils import sign_payload
from voteit.export_import.exporter import Exporter
from voteit.export_import.importer import Importer
from voteit.core.rest_api.lock import LockAlreadyRunning
from voteit.core.rest_api.lock import LockCooldownActive
from voteit.export_import.rest_api.lock import import_lock
from voteit.export_import.rest_api.lock import import_preview_lock
from voteit.export_import.rest_api.serializers import CloneSerializer
from voteit.export_import.rest_api.serializers import ImportFileSerializer
from voteit.export_import.rest_api.serializers import ExportFileSerializer
from voteit.export_import.utils import direct_clone
from voteit.export_import.utils import prepare_clone_importer
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR


@router.register("meeting-data", basename="meeting-data")
class MeetingDataViewSet(VerboseAutoPermissionViewSetMixin, viewsets.GenericViewSet):
    serializer_class = ImportFileSerializer
    parser_classes = (MultiPartParser, FileUploadParser)
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "yaml": None,
        "import_file": None,
        "clone": None,
    }

    def get_queryset(self):
        return Meeting.objects.filter(
            roles__user=self.request.user, roles__assigned__contains=ROLE_MODERATOR
        )

    def list(self, request, *args, **kwargs):
        return Response(
            data=[{"pk": o.pk, "title": o.title} for o in self.get_queryset()]
        )

    def _preview_response(self, importer: Importer, signature_valid: bool = None):
        data = importer.data.dict(exclude_unset=True, exclude={"sign"})
        if signature_valid is not None:
            data["signature_valid"] = signature_valid
            data["size_limit"] = (
                MAX_IMPORT_BYTES if signature_valid else MAX_UNSIGNED_IMPORT_BYTES
            )
        return Response(data=data, status=status.HTTP_200_OK)

    @action(
        methods=["POST"],
        detail=True,
        url_path="import",
    )
    def import_file(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={"meeting": instance, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        preview = serializer.validated_data["preview"]
        lock = import_preview_lock if preview else import_lock

        try:
            lock.acquire(request)
        except LockAlreadyRunning as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except LockCooldownActive as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        try:
            file_obj = request.data["file"]
            signature_valid = getattr(file_obj, "_signature_valid", False)
            try:
                importer = Importer(
                    instance,
                    verify=False,
                    **{
                        k: v
                        for k, v in serializer.data.items()
                        if k not in ("file", "preview")
                    },
                )
                importer.from_stream(file_obj)
            except PydanticValidationError as exc:
                raise pydantic_to_drf_validation_error(exc)
            except (ImportFileError, SignatureVerificationFailed, ReaderError) as exc:
                raise ValidationError(str(exc))
            if preview:
                return self._preview_response(importer, signature_valid=signature_valid)
            if not (importer.data.groups or importer.data.agenda_items):
                raise ValidationError(
                    {"file": ["File doesn't contain any agenda items or groups"]}
                )
            with transaction.atomic(durable=True):
                importer.run()
            return Response(
                data=importer.stats().dict(),
                status=status.HTTP_200_OK,
            )
        finally:
            lock.release(request)

    @action(
        methods=["POST"],
        detail=True,
        parser_classes=[JSONParser, MultiPartParser],
        serializer_class=CloneSerializer,
    )
    def clone(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance.is_upcoming:
            raise ValidationError(
                {"detail": "Target meeting must be in upcoming state."}
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        source = serializer.validated_data["source"]
        preview = serializer.validated_data["preview"]
        clone_kwargs = {
            k: v
            for k, v in serializer.validated_data.items()
            if k not in ("source", "preview")
        }
        lock = import_preview_lock if preview else import_lock

        try:
            lock.acquire(request)
        except LockAlreadyRunning as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except LockCooldownActive as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        try:
            if preview:
                importer = prepare_clone_importer(
                    source=source, target=instance, **clone_kwargs
                )
                return self._preview_response(importer)
            importer = direct_clone(
                source=source, target=instance, dry_run=False, **clone_kwargs
            )
            return Response(data=importer.stats().dict(), status=status.HTTP_200_OK)
        except PydanticValidationError as exc:
            raise pydantic_to_drf_validation_error(exc)
        finally:
            lock.release(request)

    @action(
        methods=["GET"],
        detail=True,
        serializer_class=ExportFileSerializer,
    )
    def yaml(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
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
