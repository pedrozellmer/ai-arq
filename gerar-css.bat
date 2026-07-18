@echo off
REM Regenera o tailwind.min.css a partir de todos os HTML/JS do site.
REM Rode este script sempre que uma classe Tailwind NOVA for usada em alguma
REM página (senão ela não terá estilo). O binário fica fora do repo.
REM Download: https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17
REM (arquivo tailwindcss-windows-x64.exe, renomeie para tailwindcss.exe)

where tailwindcss.exe >nul 2>&1
if errorlevel 1 (
  echo ERRO: tailwindcss.exe nao encontrado no PATH nem na pasta atual.
  echo Baixe em https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17
  exit /b 1
)
tailwindcss.exe -c tailwind.config.js -i tailwind-input.css -o tailwind.min.css --minify
echo OK: tailwind.min.css regenerado.
