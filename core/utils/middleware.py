class CenterContextMiddleware:
    """
    Reads X-Center-ID from the request header and sets
    request.center_id for downstream use.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.center_id = request.headers.get("X-Center-ID")
        return self.get_response(request)


class CustomerProfileContextMiddleware:
    """
    Reads X-Customer-Profile-ID from the request header and sets
    request.customer_profile_id for downstream usage.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.customer_profile_id = request.headers.get("X-Customer-Profile-ID")
        return self.get_response(request)
