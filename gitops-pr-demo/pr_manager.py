class PRManager:

    def __init__(self, github_client):
        self.github = github_client

    def find_open_pr(self, branch):

        pulls = self.github.repo.get_pulls(
            state="open",
            head=f"{self.github.repo.owner.login}:{branch}"
        )

        pulls = list(pulls)

        if pulls:
            return pulls[0]

        return None

    def find_open_pr_by_file(self, file_path):

        pulls = self.github.repo.get_pulls(state="open")

        for pr in pulls:

            for file in pr.get_files():

                if file.filename == file_path:

                    return {
                        "pr": pr,
                        "branch": pr.head.ref
                    }

        return None
    
    def create_pr(self, branch, title, body):

        pr = self.github.repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base="main"
        )

        return {
            "url": pr.html_url,
            "number": pr.number
        }