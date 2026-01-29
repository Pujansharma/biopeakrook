class CenterContextMiddleware:
    """
    Reads X-Center-ID from the request header and sets
    request.center_id for downstream use.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.center_id = request.headers.get('X-Center-ID')
        return self.get_response(request)
