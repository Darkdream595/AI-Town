"""AI Town FastAPI 主入口

提供 REST API 和 WebSocket 服务
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(
    title="AI Town Backend",
    description="AI 小镇权威世界服务器",
    version="0.1.0"
)

# CORS 配置（本地开发）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "ai-town-backend",
        "version": "0.1.0"
    }


@app.get("/")
async def root():
    """根路径"""
    return {"message": "AI Town Backend is running"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
