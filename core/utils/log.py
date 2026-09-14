import logging
from logging import getLogger

from django.core.management.color import no_style
from django.utils.log import ServerFormatter

BASIC_FORMAT = "[%(levelname)s] %(name)s:%(message)s"

logging.basicConfig(format=BASIC_FORMAT, level=logging.INFO)


class BaseFormatter(ServerFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style = no_style()


logger = getLogger()
