from fastapi import FastAPI
from contextlib import asynccontextmanager
from api.routes import graph, visualization, chat, live_feed, reports, weather, news, signals


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    graph.driver.close()
    chat.close_agent()


app = FastAPI(title="Intelligence Graph", lifespan=lifespan)
app.include_router(graph.router)
app.include_router(visualization.router)
app.include_router(chat.router)
app.include_router(live_feed.router)
app.include_router(reports.router)
app.include_router(weather.router)
app.include_router(news.router)
app.include_router(signals.router)
