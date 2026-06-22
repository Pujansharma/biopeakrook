def response_format(detail, data=None):
    context = {"detail": detail}
    if data is not None:
        if all(key in data for key in ["count", "next", "previous", "results"]):
            results = data.pop("results")
            return {**context, **data, "data": results}
        return {**context, "data": data}
    return context


def get_request_ip_address(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_request_user_agent(request):
    return request.META.get("HTTP_USER_AGENT")