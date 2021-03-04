from beer_garden import config
from beer_garden.filters.permission_mapper import PermissionRequiredAccess, Permissions
from brewtils.errors import AuthorizationRequired
from brewtils.models import Principal, Operation


def principal_filtering(
    obj: Principal = None, raise_error: bool = True, current_user: Principal = None
):
    """
    Local Admins can edit any User account
    Current User can only edit their account

    Args:
        obj: Principal model to be modified
        raise_error: If an Exception should be raised if not matching
        current_user: Principal record associated with the Operation

    Returns:

    """

    if obj.id == current_user.id:
        return obj

    for permission in current_user.permissions:
        if (
            permission.access in PermissionRequiredAccess[Permissions.LOCAL_ADMIN]
            and permission.garden == config.get("garden.name")
            and permission.namespace is None
        ):
            return obj

    if raise_error:
        raise AuthorizationRequired(
            "Action Local Garden Admin permissions or be the user being modified in the request"
        )

    return None


# Must be the Local Admin to run this


def operation_filtering(
    obj: Operation = None, raise_error: bool = True, current_user: Principal = None
):
    """
    Local Admins can edit any User account
    Current User can only edit their account

    Args:
        obj: Operation model to be modified
        raise_error: If an Exception should be raised if not matching
        current_user: Principal record associated with the Operation

    Returns:

    """

    if obj.operation_type == "USER_UPDATE":
        if current_user.id == obj.kwargs["user_id"]:
            return obj

    if obj.operation_type in ["USER_UPDATE_ROLE", "USER_REMOVE_ROLE", "USER_UPDATE"]:
        for permission in current_user.permissions:

            # Scope = Local Admins must have Admin over just the Garden
            if (
                permission.access in PermissionRequiredAccess[Permissions.LOCAL_ADMIN]
                and permission.garden == config.get("garden.name")
                and permission.namespace is None
            ):
                return obj

    if raise_error:
        raise AuthorizationRequired(
            "Action Local Garden Admin permissions or be the user being modified in the request"
        )

    return None


obj_principal_filtering = {
    Operation: operation_filtering,
    Principal: principal_filtering,
}


def model_principal_filter(
    obj=None,
    raise_error: bool = True,
    current_user: Principal = None,
):
    """
    Filters the Brewtils Model based on Principal specific rules
    Args:
        obj: Brewtils model to Filter
        raise_error: If an Exception should be raised if not matching
        current_user: Principal record associated with the Operation

    Returns:

    """

    # Impossible to add filters, so we return the object
    if not hasattr(obj, "schema"):
        return obj

    if type(obj) in obj_principal_filtering.keys():
        return obj_principal_filtering[type(obj)](
            obj=obj, raise_error=raise_error, current_user=current_user
        )

    return obj
