from django.db import models

from core.utils.models import BaseModel


class Sequence(BaseModel):
    name: str = models.CharField(
        max_length=50, db_index=True, primary_key=True, editable=False
    )
    last_value: int = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.last_value})"

    def clean(self):
        setattr(self, "name", self.name.lower())
