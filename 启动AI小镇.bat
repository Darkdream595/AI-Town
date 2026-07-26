@echo off
chcp 65001 >nul
title AI 小镇

echo ========================================
echo           AI 小镇启动器
echo ========================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

REM 检查 Node.js 是否安装
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js
    pause
    exit /b 1
)

echo [1/4] 检查 Python 虚拟环境...
if not exist "backend\venv" (
    echo [信息] 创建 Python 虚拟环境...
    python -m venv backend\venv
)

echo [2/4] 安装后端依赖...
call backend\venv\Scripts\activate
pip install -r backend\requirements.txt -q

echo [3/4] 检查前端依赖...
cd frontend
if not exist "node_modules" (
    echo [信息] 安装前端依赖...
    call npm install
)
cd ..

echo [4/4] 启动服务...
echo.
echo ========================================
echo 后端服务: http://localhost:8000
echo 前端服务: http://localhost:5173
echo ========================================
echo.
echo 按 Ctrl+C 可停止服务
echo.

REM 启动后端（新窗口）
start "AI Town Backend" cmd /k "cd /d %CD% && backend\venv\Scripts\activate && python backend\src\main.py"

REM 等待后端启动
timeout /t 3 /nobreak >nul

REM 启动前端（新窗口）
start "AI Town Frontend" cmd /k "cd /d %CD%\frontend && npm run dev"

REM 等待前端启动
timeout /t 5 /nobreak >nul

REM 打开浏览器
start http://localhost:5173

echo.
echo [完成] AI 小镇已启动！
echo.
echo 提示：按 F11 进入全屏模式以获得最佳游戏体验
echo.
pause
