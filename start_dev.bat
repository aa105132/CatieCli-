@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ====================================
echo   CatieCli 开发环境启动脚本
echo ====================================
echo.

cd /d "%~dp0"

REM 检查 Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 检查 Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js 18+
    pause
    exit /b 1
)

echo [信息] 检查后端依赖...
cd backend
if not exist "venv" (
    echo [信息] 创建 Python 虚拟环境...
    python -m venv venv
)

echo [信息] 激活虚拟环境并安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt -q

REM 确保 .env 文件存在
if not exist ".env" (
    echo [信息] 创建 .env 配置文件...
    (
        echo # CatieCli 配置文件
        echo.
        echo # 管理员账号
        echo ADMIN_USERNAME=admin
        echo ADMIN_PASSWORD=123456
        echo.
        echo # JWT 密钥
        echo SECRET_KEY=catiecli-dev-secret-key-2024
        echo.
        echo # 服务端口
        echo PORT=5001
        echo.
        echo # Google OAuth 配置
        echo GOOGLE_CLIENT_ID=681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com
        echo GOOGLE_CLIENT_SECRET=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
    ) > .env
)

REM 确保 static/assets 目录存在
if not exist "static\assets" (
    echo [信息] 创建 static/assets 目录...
    mkdir "static\assets"
)

cd ..

echo [信息] 检查前端依赖...
cd frontend
if not exist "node_modules" (
    echo [信息] 安装前端依赖...
    call npm install
)

echo [信息] 构建前端...
call npm run build

REM 复制构建产物到后端 static 目录
echo [信息] 复制前端构建产物...
xcopy /e /i /y "dist\*" "..\backend\static\" >nul

cd ..

echo.
echo ====================================
echo   启动 CatieCli 服务
echo ====================================
echo.
echo   管理员账号: admin
echo   管理员密码: 123456
echo.
echo   访问地址: http://localhost:5001
echo ====================================
echo.

cd backend
call venv\Scripts\activate.bat
python run.py