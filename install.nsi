SetCompressor /SOLID lzma
Name "vcontainer"
OutFile "install.exe"
RequestExecutionLevel user
Section
  SetOutPath "$TEMP\vcontainer"
  File /r /x .git /x install.exe "*"
  ExecWait 'powershell -ExecutionPolicy Bypass -File "$TEMP\vcontainer\install.ps1"'
SectionEnd
; Build with: makensis install.nsi
; Unsigned output may trigger a Windows SmartScreen warning.
