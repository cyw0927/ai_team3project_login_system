@echo off
setlocal
cd /d "%~dp0\.."

echo ==========================================
echo AX 평가 시스템 - 로컬 실행
echo ==========================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv가 없습니다.
    echo 먼저 tools\setup_project.bat 를 실행하세요.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo [INFO] .env.example을 복사해 .env를 만들었습니다.
    )
)

echo.
echo [1/3] Django 설정 검사
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

echo.
echo [2/3] Migration 적용
python manage.py migrate
if errorlevel 1 goto :fail

echo.
echo [3/3] 서버 실행
echo 브라우저 주소: http://127.0.0.1:8000/
echo 종료: Ctrl+C
echo.
python manage.py runserver
goto :eof

:fail
echo.
echo [ERROR] 실행 준비 중 오류가 발생했습니다.
pause
exit /b 1
