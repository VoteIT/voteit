class OrgPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.organisation.models import Organisation
    >>> find_bad_permission_names(OrgPermissions, Organisation)

    """

    ADD = "organisation.add_organisation"  # FIXME
    CHANGE = "organisation.change_organisation"
    DELETE = "organisation.delete_organisation"
    VIEW = "organisation.view_organisation"
    MANAGE = "organisation.manage_organisation"
