import asyncio
from fastapi import FastAPI
import uvicorn

app = FastAPI()


@app.on_event("startup")
async def startup():
    loop = asyncio.new_event_loop()
    print("New event loop is:", type(loop))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
