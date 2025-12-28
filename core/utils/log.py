from django.core.management.color import no_style
from django.utils.log import ServerFormatter


class BaseFormatter(ServerFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style = no_style()
