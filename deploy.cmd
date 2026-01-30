@echo off
echo RUNNING RUFF
call ruff check src
if %ERRORLEVEL% neq 0 (
    echo Ruff  found errors. Stopping the build and deploy process.
    exit /b 1
)
echo Starting build and deploy process...
echo.
echo RUNNING BUILD
call sam build
if %ERRORLEVEL% neq 0 (
    echo Build failed at: %date% %time%
    exit /b 1
)
echo RUNNING DEPLOY
call sam deploy
if %ERRORLEVEL% neq 0 (
    echo Deploy failed at: %date% %time%
    exit /b 1
)
echo Deploy completed successfully at: %date% %time%
