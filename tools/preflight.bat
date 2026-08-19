@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
chcp 65001 > nul

echo ==========================================
echo  AX 평가 시스템 - 실행 전 자동 점검
echo ==========================================

echo.
echo [1/8] 프로젝트 파일 확인
if not exist manage.py (
  echo [FAIL] manage.py가 없습니다.
  goto :fail
)
if not exist requirements.txt (
  echo [FAIL] requirements.txt가 없습니다.
  goto :fail
)
echo [OK] 프로젝트 루트 정상

echo.
echo [2/8] 가상환경 확인
if not exist ".venv\Scripts\python.exe" (
  echo [FAIL] .venv가 없습니다.
  echo 먼저 tools\setup_project.bat 를 실행하세요.
  goto :fail
)
set "PYTHON=.venv\Scripts\python.exe"
"%PYTHON%" --version || goto :fail

echo.
echo [3/8] .env 확인
if not exist .env (
  echo [FAIL] .env가 없습니다.
  echo .env.example을 복사한 뒤 실제 DB/OAuth 값을 입력하세요.
  goto :fail
)
echo [OK] .env 존재

echo.
echo [4/8] 정적 구조 검사
"%PYTHON%" tools\pre_release_check.py || goto :fail

echo.
echo [5/8] Django 설정 검사
"%PYTHON%" manage.py check || goto :fail

echo.
echo [6/8] PostgreSQL 연결/스키마 검사
"%PYTHON%" manage.py check_database_setup || goto :fail

echo.
echo [7/8] Migration 적용 상태 확인
"%PYTHON%" manage.py showmigrations dashboard || goto :fail
"%PYTHON%" manage.py makemigrations --check --dry-run dashboard || goto :fail

echo.
echo [8/8] Dashboard 테스트
"%PYTHON%" manage.py test dashboard -v 1 || goto :fail

echo.
echo ==========================================
echo  [PASS] 실행 준비 완료
 echo ==========================================
echo.
echo 로컬 실행: tools\run_local.bat
echo 팀원 공유: tools\run_team_test.bat
exit /b 0

:fail
echo.
echo ==========================================
echo  [FAIL] 위 단계에서 오류가 발생했습니다.
echo ==========================================
exit /b 1
