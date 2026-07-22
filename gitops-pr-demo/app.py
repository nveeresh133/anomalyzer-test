from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from models import RecommendationRequest
from services.recommendation_service import RecommendationService
from github_client import GitHubClient
from branch_manager import BranchManager

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.post("/recommendation/apply")
def apply_recommendation(request: RecommendationRequest):

    service = RecommendationService()

    return service.apply(request)


@app.get("/github/test")
def github_test():
    github = GitHubClient()
    return github.test_connection()


@app.get("/github/files")
def github_files():
    github = GitHubClient()
    return github.list_files()


@app.get("/github/read")
def github_read():
    github = GitHubClient()
    return github.read_file("README.md")


@app.post("/branch/create")
def create_branch():

    github = GitHubClient()

    branch = BranchManager.generate_branch_name(
        resource="storage",
        recommendation="hot-to-cool"
    )

    return github.create_branch(branch)

@app.get("/github/pullrequests")
def get_pull_requests():

    github = GitHubClient()

    pulls = github.list_pull_requests()

    return pulls