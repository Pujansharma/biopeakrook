from typing import cast, Type

from django.contrib.auth import (
    authenticate as django_authenticate,
    get_user_model as django_get_user_model,
)
from django.views.decorators.debug import sensitive_variables

from accounts.users.models import User as UserModel


# Override get_user_model to return the correct type
@sensitive_variables("credentials")
def authenticate(request=None, **credentials) -> "UserModel | None":
    """
    Return the User model that is properly typed.
    Returns User if credentials are valid, otherwise None
    :return: User
    :rtype: 'UserModel | None'
    """
    return cast("UserModel", django_authenticate(request=request, **credentials))


# Override authenticate to return the correct type
def get_user_model() -> Type["UserModel"]:
    """
    Return the User model that is active in this project.
    Properly typed to return our custom User model instead of AbstractUser.
    :rtype: Type['UserModel']
    """
    return cast("Type[UserModel]", django_get_user_model())
