from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
import uvicorn

app = FastAPI(
    title=settings.app_name,
    description="AI-Powered Accounting Automation Platform",
    version="0.1.0",
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["|*"],
    allow_headers=["*"]
)

@app.get("/")
def read_root():
    return {
        "message": f"Server of {settings.app_name} is working!",
        "status": "active",
        "version": "0.1.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.app_env
    }

@app.on_event("startup")
async def startup_event():
    print("=" * 50)
    print(f"Starting {settings.app_name}")
    print(f"Environment: {settings.app_env}")
    print(f"Debug Mode: {settings.debug}")
    print("=" * 50)

@app.on_event("shutdown")
async def shutdown():
    print(f"Shutting down {settings.app_name}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )