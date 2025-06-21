from django.db import models
from django.utils import timezone

class Repository(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=200, unique=True)

    def __str__(self) -> str:
        return self.name

class ChangelogEntry(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='changelog_entries', default=1)
    title = models.CharField(max_length=255)
    content_html = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.title