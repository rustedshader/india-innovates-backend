from fastapi import FastAPI
from contextlib import asynccontextmanager
from api.routes import graph, visualization


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    graph.driver.close()


app = FastAPI(title="Intelligence Graph", lifespan=lifespan)
app.include_router(graph.router)
app.include_router(visualization.router)
