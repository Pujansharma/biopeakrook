from django.db.models import Func, Value


class ExtractPartText(Func):
    function = "SPLIT_PART"

    def __init__(self, expression, delimiter=Value(" "), index=Value("1"), **extra):
        super().__init__(expression, delimiter, index, **extra)
