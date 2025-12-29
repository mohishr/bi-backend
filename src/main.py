from fastapi import FastAPI
import uvicorn

# Import your API routers
from apis.file_store_api import router as file_router
from apis.vector_search_api import router as vector_search_router
# from user_api import router as user_router
# from auth_api import router as auth_router
# Add more routers here...

from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost",
    "http://localhost:5173", # <-- Add your frontend origin here
]

def create_app() -> FastAPI:
    app = FastAPI(title="My Modular FastAPI Application")

    # Register routers
    app.include_router(file_router, prefix="/files", tags=["File Service"])
    app.include_router(vector_search_router, prefix="/search", tags=["Vector Search"])
    # app.include_router(user_router, prefix="/users", tags=["Users"])
    # app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    # Add more include_router() calls here...

    return app


app = create_app()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,         # Allows specific origins
    allow_credentials=True,        # Allows cookies/authorization headers to be included in requests
    allow_methods=["GET", "POST", "PUT", "DELETE"], # Allows specific HTTP methods
    allow_headers=["*"],           # Allows all headers
)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
