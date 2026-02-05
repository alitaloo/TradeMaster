@echo off
REM TradeMaster Gateway Sync - Windows Batch
REM 使用方法: 在啟動 OpenClaw 前先執行此腳本

echo ========================================
echo   TradeMaster Gateway 版本檢查
echo ========================================
echo.

node "%~dp0gateway_sync.js"

if %errorlevel% neq 0 (
  echo.
  echo ⚠️  版本同步失敗，請檢查錯誤訊息
  pause
  exit /b %errorlevel%
)

echo.
echo ✅ 可以安全啟動 OpenClaw 了！
echo.
pause
