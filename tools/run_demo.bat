@echo off
setlocal
cd /d "%~dp0\.."

echo ==========================================
echo AX 평가 시스템 - 데모 데이터 실행
echo ==========================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv가 없습니다.
    echo 먼저 tools\setup_project.bat 를 실행하세요.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

if not exist ".env" (
    if exist ".env.example" copy /Y ".env.example" ".env" >nul
)

python manage.py check
if errorlevel 1 goto :fail

echo.
echo [DB] PostgreSQL 스키마 준비
python manage.py prepare_postgres
if errorlevel 1 goto :fail

echo.
echo [DB] PostgreSQL 연결 점검
python manage.py check_database_setup
if errorlevel 1 goto :fail

python manage.py migrate
if errorlevel 1 goto :fail

echo.
echo [주의] 아래 명령은 데모 데이터를 생성/재생성합니다.
python manage.py seed_demo
if errorlevel 1 goto :fail

echo.
echo 관리자: admin01 / admin1234!
echo 학생: student01 / test1234!
echo 주소: http://127.0.0.1:8000/
echo.
python manage.py runserver
goto :eof

:fail
echo.
echo [ERROR] 데모 실행 준비 중 오류가 발생했습니다.
pause
exit /b 1
