import os
from .changelog_utils import ChangelogGenerator
import django
from django.utils import timezone
import questionary
from rich.console import Console
from rich.panel import Panel
import subprocess
import re
from github import Github
from github.GithubException import GithubException
import dotenv
from datetime import datetime, timedelta

# Environment setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "delta.settings")
django.setup()

from .models import *
from website.models import ChangelogEntry
from datetime import timezone as dt_timezone

# Load environment variables
dotenv.load_dotenv()
console = Console()

def get_current_repo_info():
    """Get the current repository's owner and repo name from git config."""
    try:
        remote_url = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url'], text=True).strip()
        match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', remote_url)
        if match:
            return {"owner": match.group(1), "repo": match.group(2)}
    except subprocess.CalledProcessError:
        return None
    return None

def repository_exists(owner, repo, token):
    """Verify if a GitHub repository exists."""
    try:
        g = Github(token)
        g.get_repo(f"{owner}/{repo}")
        return True
    except GithubException:
        return False

def main():
    try:
        # Check environment variables
        github_token = os.getenv("GITHUB_TOKEN")
        greptile_token = os.getenv("GREPTILE_API_KEY")
        if not github_token or not greptile_token:
            console.print(Panel(
                "[red]Missing required environment variables: GITHUB_TOKEN and/or GREPTILE_API_KEY. Add them to website/keys.env[/red]",
                border_style="red", padding=(1, 1)
            ))
            return

        # Instantiate ChangelogGenerator
        changelog_generator = ChangelogGenerator()

        # Get repository information
        current_repo = get_current_repo_info()
        default_repo = f"{current_repo['owner']}/{current_repo['repo']}" if current_repo else ""
        
        while True:
            repo_input = questionary.text(
                "Enter repository format: owner/repo",
                default=default_repo
            ).ask()
            if not repo_input or "/" not in repo_input:
                console.print("[red]Please enter in owner/repo format (e.g., user/repo)[/red]")
                continue
            owner, repo = repo_input.split("/", 1)
            if not owner or not repo:
                console.print("[red]Invalid repository format. Use owner/repo format.[/red]")
                continue
            if not repository_exists(owner, repo, github_token):
                console.print(f"[red]Repository {owner}/{repo} not found. Please check the name and your permissions.[/red]")
                continue
            repo_url = f"https://github.com/{owner}/{repo}"
            break

        # Choose input type
        input_type_options = [
            {"name": "Number of commits", "value": "integer"},
            {"name": "Date range", "value": "date"}
        ]
        input_type = questionary.select(
            "How would you like to specify the changelog range?",
            choices=[questionary.Choice(title=f"{opt['name']} ({opt['value']})", value=opt['value']) for opt in input_type_options]
        ).ask()

        # Get commit range or date range
        if input_type == "integer":
            number_of_commits = int(questionary.text(
                "Enter number of commits to fetch",
                default="1"
            ).ask())
            try:
                commits = changelog_generator.fetch_commits(repo_url, number_of_commits=number_of_commits)
            except Exception as e:
                console.print(Panel(
                    f"[red]Failed to fetch commits: {str(e)}[/red]",
                    border_style="red", padding=(1, 1)
                ))
                return
        else:
            date_range_options = [
                {"name": "Preset range", "value": "preset"},
                {"name": "Custom range", "value": "custom"}
            ]
            date_range_type = questionary.select(
                "How would you like to specify the date range?",
                choices=[questionary.Choice(title=f"{opt['name']} ({opt['value']})", value=opt['value']) for opt in date_range_options]
            ).ask()
            if date_range_type == "preset":
                preset_choices = [
                    {"name": "24 hours", "value": 1},
                    {"name": "5 days", "value": 5},
                    {"name": "10 days", "value": 10},
                    {"name": "30 days", "value": 30}
                ]
                days = questionary.select(
                    "Select date range",
                    choices=[questionary.Choice(title=f"{opt['name']} ({opt['value']})", value=opt['value']) for opt in preset_choices]
                ).ask()
                end_date = datetime.now()
                start_date = (end_date - timedelta(days=days)).strftime("%Y-%m-%d")
                end_date = end_date.strftime("%Y-%m-%d")
            else:
                start_date = questionary.text(
                    "Enter start date (YYYY-MM-DD)",
                    default=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                ).ask()
                end_date = questionary.text(
                    "Enter end date (YYYY-MM-DD)",
                    default=datetime.now().strftime("%Y-%m-%d")
                ).ask()
            try:
                commits = changelog_generator.fetch_commits(repo_url, start_date=start_date, end_date=end_date)
            except Exception as e:
                console.print(Panel(
                    f"[red]Failed to fetch commits: {str(e)}[/red]",
                    border_style="red", padding=(1, 1)
                ))
                return

        # Generate changelog
        console.print("[blue]Generating changelog, please wait...[/blue]")
        
        try:
            changes = changelog_generator.generate_changelog(
                commits,
                greptile_token=greptile_token,
                github_token=github_token,
                repo=f"{owner}/{repo}",
                branch="main",
                session_id=None
            )

            # Check for no changes
            is_no_changes = len(commits) == 0  # Check if commits list is empty

            if is_no_changes:
                console.print(
                    Panel(
                        "[yellow]No commits found for the specified range or number of commits. No changelog will be saved to the database.[/yellow]",
                        title="Warning",
                        border_style="yellow",
                        padding=(1, 1)
                    )
                )
                return  # Exit the function if no commits

            # Format and display changelog
            formatted_changes = (
                changes
                .replace(r"\*\*(.*?)\*\*", r"[bold]\1[/bold]")  # Bold
                .replace(r"\*(.*?)\*", r"[italic]\1[/italic]")  # Italic
                .replace(r"^## No Changes Found$", r"[red bold]NO CHANGELOG[/red bold]", 1)  # No changes title
                .replace(r"\*Generated on (.*?)\*", r"[dim]Generated on \1[/dim]")  # Date
            )

            console.print(
                Panel(
                    formatted_changes,
                    title="Changelog",
                    title_align="center",
                    border_style="green",
                    padding=(1, 1)
                )
            )

            # Determine the earliest commit date for started_at
            earliest_date = None
            if commits:  # Ensure commits list is not empty
                commit_dates = [datetime.strptime(commit['date'], "%Y-%m-%dT%H:%M:%SZ") for commit in commits]
                if commit_dates:
                    # Make the datetime object timezone-aware
                    earliest_date = timezone.make_aware(min(commit_dates), dt_timezone.utc)
                else:
                    earliest_date = None

            # Save to database
            title = questionary.text(
                "Enter changelog title",
                default="Changelog"
            ).ask()
            # Get or create the Repository instance
            repo_instance, _ = Repository.objects.get_or_create(
                name=f"{owner}/{repo}",
                url=repo_url
            )

            changelog_entry = ChangelogEntry(
                repository=repo_instance,
                title=title,
                content_html=changes,
                created_at=timezone.now(),
                updated_at=timezone.now(),
                started_at=earliest_date
            )
            changelog_entry.save()
            console.print(f"[green]✔ Changelog saved to database with title: {title}[/green]")

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Failed to generate changelog: {str(e)}[/red]",
                    border_style="red",
                    padding=(1, 1)
                )
            )

    except Exception as e:
        console.print(
            Panel(
                f"[red]Failed to generate changelog: {str(e)}[/red]",
                border_style="red",
                padding=(1, 1)
            )
        )

if __name__ == "__main__":
    main()