@echo off
title MySQL 8.4 Server

rem ============================================================
rem  MYSQL_HOME auto-detect order:
rem    1. existing MYSQL_HOME environment variable
rem    2. portable unzip dir C:\mysql\mysql-8.4.0-winx64
rem    3. official installer dirs 8.4 / 8.0
rem  MYSQL_DATA  data dir (default: current user profile)
rem  MYSQL_PWD   root password
rem ============================================================
if not exist "%MYSQL_HOME%\bin\mysqld.exe" set "MYSQL_HOME=C:\mysql\mysql-8.4.0-winx64"
if not exist "%MYSQL_HOME%\bin\mysqld.exe" set "MYSQL_HOME=C:\Program Files\MySQL\MySQL Server 8.4"
if not exist "%MYSQL_HOME%\bin\mysqld.exe" set "MYSQL_HOME=C:\Program Files\MySQL\MySQL Server 8.0"
set "MYSQL_DATA=%USERPROFILE%\mysql-data"
set "MYSQL_PWD=root123"

if not exist "%MYSQL_HOME%\bin\mysqld.exe" (
    echo [ERROR] %MYSQL_HOME%\bin\mysqld.exe not found.
    echo Set MYSQL_HOME env var, or add your install dir to the detect list above.
    pause
    exit /b 1
)

rem check if already running
tasklist /FI "IMAGENAME eq mysqld.exe" 2>NUL | find /I "mysqld.exe" >NUL
if %ERRORLEVEL%==0 (
    echo MySQL is already running, nothing to do.
    pause
    exit /b 0
)

echo Starting MySQL 8.4 ...
echo   Home: %MYSQL_HOME%
echo   Data: %MYSQL_DATA%
start "" /min "%MYSQL_HOME%\bin\mysqld.exe" --datadir="%MYSQL_DATA%" --console

timeout /t 3 /nobreak >nul

"%MYSQL_HOME%\bin\mysql.exe" -u root -p%MYSQL_PWD% -e "SELECT VERSION();" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo MySQL started successfully. Database: hr_system
) else (
    echo MySQL may still be starting, try again in a few seconds.
)
pause
