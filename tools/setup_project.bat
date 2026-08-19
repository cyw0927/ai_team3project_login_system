@echo off
cd /d "%~dp0\.."
chcp 65001 > nul
setlocal

echo.
echo ==========================================
echo  AX 평가 시스템 초기 설정
echo ==========================================

if not exist manage.py (
  echo 오류: manage.py가 있는 프로젝트 루트에서 실행하세요.
  exit /b 1
)

if not exist .venv (
  echo [1/8] 가상환경 생성
  python -m venv .venv || exit /b 1
) else (
  echo [1/8] 기존 .venv 사용
)

echo [2/8] 가상환경 Python 사용
set PYTHON=.venv\Scripts\python.exe

echo [3/8] pip 업데이트
%PYTHON% -m pip install --upgrade pip || exit /b 1

echo [4/8] 패키지 설치
%PYTHON% -m pip install -r requirements.txt || exit /b 1

if not exist .env (
  echo [5/8] .env.example -^> .env 생성
  copy .env.example .env > nul
) else (
  echo [5/8] 기존 .env 사용
)

echo [6/8] Django 검사
%PYTHON% manage.py check || exit /b 1
echo [DB] PostgreSQL 스키마 준비
%PYTHON% manage.py prepare_postgres || exit /b 1
echo [DB] PostgreSQL 연결 점검
%PYTHON% manage.py check_database_setup || exit /b 1

echo [7/8] Migration
%PYTHON% manage.py migrate || exit /b 1

echo [8/8] 자동 테스트
%PYTHON% manage.py test dashboard -v 2 || exit /b 1

echo.
echo ==========================================
echo  초기 설정 완료
echo ==========================================
echo.
echo 기본 실행:
echo %PYTHON% manage.py runserver
echo.
echo 데모 데이터:
echo %PYTHON% manage.py seed_demo
