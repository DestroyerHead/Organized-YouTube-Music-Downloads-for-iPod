@echo off
rem Instalado: usa o Python que vem com o programa. Sem instalador: o Python do PC.
if exist "%~dp0..\python\python.exe" (
  "%~dp0..\python\python.exe" "%~dp0host.py"
) else (
  py -3 "%~dp0host.py"
)
