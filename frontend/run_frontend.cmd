@echo off
cd /d "%~dp0"
node node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173 > vite.out.log 2> vite.err.log
