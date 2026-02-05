from dataclasses import dataclass


@dataclass
class ContentTypeAccessor:
    label: str
    org_path: str


history_content_type_registry = list[ContentTypeAccessor]()


def history_log(org_path: str):
    if not isinstance(org_path, str):
        raise TypeError("org_path must be a string")

    def wrapper(cls):
        history_content_type_registry.append(
            ContentTypeAccessor(cls._meta.label_lower, org_path)
        )
        return cls

    return wrapper
