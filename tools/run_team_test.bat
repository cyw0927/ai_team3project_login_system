@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
chcp 65001 > nul

echo ==========================================
echo  AX 평가 시스템 - 팀원 공유 실행
 echo ==========================================

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv가 없습니다.
  echo 먼저 tools\setup_project.bat 를 실행하세요.
  pause
  exit /b 1
)
set "PYTHON=.venv\Scripts\python.exe"

if not exist .env (
  echo [ERROR] .env가 없습니다.
  echo DB/OAuth 설정을 먼저 완료하세요.
  pause
  exit /b 1
)

echo.
echo [1/4] Django 설정 확인
"%PYTHON%" manage.py check || goto :fail

echo.
echo [2/4] PostgreSQL 연결 확인
"%PYTHON%" manage.py check_database_setup || goto :fail

echo.
echo [3/4] Migration 적용
"%PYTHON%" manage.py migrate || goto :fail

echo.
echo [4/4] 네트워크 주소 확인
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=*" %%B in ("%%A") do echo 팀원 접속 후보: http://%%B:8000/
)

echo.
echo 서버를 0.0.0.0:8000 으로 실행합니다.
echo 같은 Wi-Fi/LAN에 있는 팀원은 위 IPv4 주소로 접속하세요.
echo 종료: Ctrl+C

echo.
"%PYTHON%" manage.py runserver 0.0.0.0:8000
goto :eof

:fail
echo.
echo [ERROR] 서버 실행 전 점검에서 실패했습니다.
pause
exit /b 1
