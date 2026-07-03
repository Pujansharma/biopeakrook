"""Per-method rate limits for pre-consultation GET/PUT/POST endpoints."""

from rest_framework.throttling import SimpleRateThrottle


class _PreConsultationMethodThrottle(SimpleRateThrottle):
    methods: frozenset[str] = frozenset()

    def allow_request(self, request, view) -> bool:
        if request.method not in self.methods:
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view) -> str | None:
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }


class PreConsultationGetThrottle(_PreConsultationMethodThrottle):
    scope = "pre_consultation_get"
    methods = frozenset({"GET"})


class PreConsultationPutThrottle(_PreConsultationMethodThrottle):
    scope = "pre_consultation_put"
    methods = frozenset({"PUT"})


class PreConsultationPostThrottle(_PreConsultationMethodThrottle):
    scope = "pre_consultation_post"
    methods = frozenset({"POST"})
