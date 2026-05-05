from rest_framework.request import Request as DefaultRequest

from accounts.utils.auth import get_user_model

UserModel = get_user_model()


# Create a custom Request type that has the user property properly typed
class Request(DefaultRequest):
    user: "UserModel"
