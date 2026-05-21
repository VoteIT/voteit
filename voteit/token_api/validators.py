from django.core.exceptions import ValidationError


def _valid_scopes_map() -> dict[str, set[str]]:
    from voteit.token_api import router

    result = {}
    standard_actions = {
        "list",
        "create",
        "retrieve",
        "update",
        "partial_update",
        "destroy",
    }
    for _prefix, viewset, basename in router.registry:
        resource = getattr(viewset, "token_api_scope", None) or basename
        actions = {a for a in standard_actions if hasattr(viewset, a)}
        actions.update(f.__name__ for f in viewset.get_extra_actions())
        result[resource] = actions
    return result


def validate_api_key_scopes(scopes: list) -> None:
    valid = _valid_scopes_map()

    for scope in scopes:
        parts = scope.split(".", 1)
        if len(parts) != 2:
            raise ValidationError(
                f"Invalid scope '{scope}': expected '<resource>.<action>'."
            )
        resource, action = parts

        if resource not in valid:
            raise ValidationError(
                f"Unknown resource '{resource}' in scope '{scope}'. "
                f"Valid resources: {sorted(valid)}."
            )

        if action != "*" and action not in valid[resource]:
            raise ValidationError(
                f"Unknown action '{action}' for resource '{resource}'. "
                f"Valid actions: {sorted(valid[resource])}."
            )
