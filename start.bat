@echo off
start "PaperHunter-Backend" cmd /k "conda activate paperhunter && cd /d %~dp0 && uvicorn backend.main:app --reload --port 8000"
start "PaperHunter-Frontend" cmd /k "cd /d %~dp0\frontend && npm run dev"
timeout /t 5 /nobreak >nul
start http://localhost:3000
