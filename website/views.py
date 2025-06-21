from django.shortcuts import render
from .models import *
import markdown


# Create your views here.
def index(request):
    # Get all repos and annotate with last_update (latest changelog entry)
    repos = Repository.objects.annotate(
        last_update=models.Max('changelog_entries__created_at')
    ).order_by('-last_update')
    
    return render(request, 'website/index.html', {'repos': repos})

def changelog_view(request, repo_id):
    repo = Repository.objects.get(id=repo_id)
    changelog_entries = repo.changelog_entries.all().order_by('-created_at')

    # Convert markdown content to HTML
    for entry in changelog_entries:
        entry.content_html = markdown.markdown(entry.content_html, extensions=['fenced_code', 'nl2br'])

    return render(request, 'website/changelog.html', {'repo': repo, 'changelog_entries': changelog_entries})

def details_view(request):
    if request.method == 'GET':
        return render(request, 'website/details.html')