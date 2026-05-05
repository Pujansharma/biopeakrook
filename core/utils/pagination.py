from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination


class BaseLimitOffsetPagination(LimitOffsetPagination):
    max_limit = 50


class BasePageNumberPagination(PageNumberPagination):
    page_size_query_param = "limit"
    max_page_size = 50
