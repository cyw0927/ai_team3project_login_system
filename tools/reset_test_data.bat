@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
chcp 65001 > nul

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv가 없습니다.
  exit /b 1
)
set "PYTHON=.venv\Scripts\python.exe"

echo ==========================================
echo  테스트 데이터 정리 메뉴
 echo ==========================================
echo 1. 랜덤 평가만 삭제
 echo 2. 더미 학생만 삭제
 echo 3. 취소
set /p CHOICE=선택:

if "%CHOICE%"=="1" (
  "%PYTHON%" manage.py delete_random_evaluations
  goto :eof
)
if "%CHOICE%"=="2" (
  "%PYTHON%" manage.py delete_dummy_students
  goto :eof
)

echo 취소했습니다.
