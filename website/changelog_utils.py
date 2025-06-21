import requests

class ChangelogGenerator:
    def __init__(self, github_token=None):
        self.github_token = github_token
        self.headers = {
            'Accept': 'application/vnd.github+json'
        }
        if github_token:
            self.headers['Authorization'] = f'token {github_token}'

    def fetch_commits(self, github_repo_url, number_of_commits=None, start_date=None, end_date=None):
        # Only allow either number_of_commits or (start_date and end_date), not both
        if number_of_commits and (start_date or end_date):
            raise ValueError("Specify either number_of_commits OR start_date/end_date, not both.")

        # Extract owner and repo name from URL
        parts = github_repo_url.rstrip('/').split('/')
        owner, repo = parts[-2], parts[-1]

        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {}

        if number_of_commits:
            params['per_page'] = number_of_commits
        elif start_date or end_date:
            if start_date:
                params['since'] = f"{start_date}T00:00:00Z"
            if end_date:
                params['until'] = f"{end_date}T23:59:59Z"
        else:
            raise ValueError("You must specify either number_of_commits or start_date/end_date.")

        # Make the API request to fetch commits
        response = requests.get(api_url, headers=self.headers, params=params)
        response.raise_for_status()
        commits = response.json()

        # Check if commits are returned and process them
        commit_data = []
        for commit in commits:
            commit_sha = commit['sha']
            commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
            commit_response = requests.get(commit_url, headers={**self.headers, 'Accept': 'application/vnd.github.v3.diff'})
            commit_response.raise_for_status()
            diff_text = commit_response.text

            commit_data.append({
                "message": commit['commit']['message'].strip(),
                "author": commit['commit']['author']['name'],
                "date": commit['commit']['author']['date'],
                "hash": commit['sha'],
                "changes": [diff_text] if diff_text else []
            })

        return commit_data
    
    def init_repository(self, greptile_token, github_token, repo, branch="main", reload=False, notify=False):
        """
        Initializes a repository in Greptile.
        """
        url = "https://api.greptile.com/v2/repositories"
        payload = {
            "reload": reload,
            "remote": "github",
            "repository": repo,
            "branch": branch,
            "notify": notify
        }
        headers = {
            "Authorization": f"Bearer {greptile_token}",
            "X-GitHub-Token": github_token,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


    def generate_changelog(self, commits, greptile_token, github_token, repo, branch="main", session_id=None):
        """
        Generates a concise technical changelog based on the provided commit messages and diffs.
        """
        # Initialize the repository in Greptile before generating the changelog
        self.init_repository(greptile_token, github_token, repo, branch=branch, reload=False, notify=False)

        # Prepare prompt for LLM with commit messages and diffs
        prompt = """
Create a concise technical changelog based on the changes provided below. The changelog must meet the following requirements:
	•	Format the changelog using markdown bullet points.
	•	Limit the output to a maximum of 7 bullet points (use less if you can).
	•	Include only the changelog entries—do not add any introductory text, explanations, summaries, or section headers (e.g., do not include “# Changelog”).
	•	The response should consist exclusively of the bullet points, with no text before or after.

Reference the following changes:


"""
        for commit in commits:
            prompt += f"Commit: {commit['message']}\n"
            prompt += f"Author: {commit['author']}\n"
            prompt += f"Date: {commit['date']}\n"
            prompt += "Changes:\n" + "\n".join(commit['changes']) + "\n\n"

        # Prepare the API request to Greptile
        url = "https://api.greptile.com/v2/query"
        payload = {
            "messages": [
                {
                    "id": "1",
                    "content": prompt,
                    "role": "user"
                }
            ],
            "repositories": [
                {
                    "remote": "github",
                    "branch": branch,
                    "repository": repo
                }
            ],
            "sessionId": session_id or "default-session",
            "stream": False,
            "genius": False
        }
        headers = {
            "Authorization": f"Bearer {greptile_token}",
            "X-GitHub-Token": github_token,
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)

        # Check for HTTP errors
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise RuntimeError("Unauthorized: Please check your Greptile and GitHub tokens.") from e
            else:
                raise
        
        # Get the first value in the response dict (it seems to be inconsistent returning "changelog", "messages", etc)
        result = response.json()
        if isinstance(result, dict) and result:
            first_value = next(iter(result.values()))
            if isinstance(first_value, list):
                # Join list elements with newlines to form a markdown string
                return "\n".join(str(item) for item in first_value)
            elif isinstance(first_value, str):
                return first_value
        return ""