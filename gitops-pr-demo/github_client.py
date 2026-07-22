from github import Github
from github.GithubException import GithubException


from config import settings


class GitHubClient:
    def __init__(self):
        self.github = Github(settings.github_token)
        self.repo = self.github.get_repo(
            f"{settings.owner}/{settings.repo}"
        )

    def create_branch(self, branch_name: str):

        base_branch = self.repo.get_branch(settings.base_branch)

        self.repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_branch.commit.sha
        )

        return {
            "branch": branch_name,
            "base": settings.base_branch,
            "commit": base_branch.commit.sha
        }
    
    def list_pull_requests(self):

        pulls = self.repo.get_pulls(state="open")

        result = []

        for pr in pulls:

            result.append({

                "number": pr.number,

                "title": pr.title,

                "url": pr.html_url,

                "branch": pr.head.ref,

                "author": pr.user.login,

                "created": str(pr.created_at)

            })

        return result

    def test_connection(self):
        """
        Verify GitHub authentication.
        """
        return {
            "repo": self.repo.full_name,
            "default_branch": self.repo.default_branch
        }

    def list_files(self, path=""):
        """
        List files/folders inside a path.
        """
        contents = self.repo.get_contents(path)

        result = []

        for item in contents:
            result.append(
                {
                    "name": item.name,
                    "path": item.path,
                    "type": item.type
                }
            )

        return result

    def update_file(self,
                file_path: str,
                branch: str,
                new_content: str,
                commit_message: str):

        file = self.repo.get_contents(
            file_path,
            ref=branch
        )

        self.repo.update_file(
            path=file_path,
            message=commit_message,
            content=new_content,
            sha=file.sha,
            branch=branch
        )

        return {
            "status": "updated",
            "branch": branch
        }
    
    def read_file(self, file_path, branch="main"):

        file = self.repo.get_contents(
            file_path,
            ref=branch
        )

        return {
            "content": file.decoded_content.decode(),
            "sha": file.sha
        }