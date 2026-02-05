from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType

from voteit.organisation.models import Organisation


@dataclass
class ContentTypeAccessor:
    label: str
    org_path: str

    def get_organisation_count(self, org: Organisation) -> int:
        """
        Get the count of objects using <org_path>=org as filter lookup.
        """
        app_label, model = self.label.split(".")
        lookup = {self.org_path: org}
        model_cls = ContentType.objects.get_by_natural_key(
            app_label, model
        ).model_class()
        return model_cls.objects.filter(**lookup).count()


history_content_type_registry = list[ContentTypeAccessor]()


def history_log(org_path: str):
    """
    Decorator for Models to include in history log for each organization.
    org_path must be a lookup string, for example 'meeting__organisation'.
    """
    if not isinstance(org_path, str):
        raise TypeError("org_path must be a string")

    def wrapper(cls):
        history_content_type_registry.append(
            ContentTypeAccessor(cls._meta.label_lower, org_path)
        )
        return cls

    return wrapper
