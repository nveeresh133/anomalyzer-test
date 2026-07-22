from dotenv import load_dotenv
import os

load_dotenv()


class Settings:

    github_token = os.getenv("GITHUB_TOKEN")

    owner = os.getenv("GITHUB_OWNER")

    repo = os.getenv("GITHUB_REPO")

    base_branch = os.getenv("BASE_BRANCH", "main")


settings = Settings()