from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(
    title="RentalManager",
    version="1.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory="backend/static"),
    name="static"
)

templates = Jinja2Templates(directory="backend/templates")


@app.get("/")
def dashboard(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="pages/dashboard.html",
        context={
            "request": request,
            "version": app.version,
            "current_page": "dashboard",
        },
    )
