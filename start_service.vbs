' Uruchamia daemon anonimizacji w tle bez widocznego okna konsoli
' (pythonw.exe zamiast okna konsoli python.exe).
' Szuka instalacji aplikacji w standardowej lokalizacji, a gdy jej nie znajdzie
' - uruchamia serwer z drzewa repo, z ktorego skrypt zostal wywolany.
Option Explicit
Dim shell, fso, appDir
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programy\Anonimizator Pism"
If Not fso.FileExists(appDir & "\app\server.py") Then appDir = fso.GetParentFolderName(WScript.ScriptFullName)

If fso.FileExists(appDir & "\.venv\Scripts\pythonw.exe") Then
    shell.Run """" & appDir & "\.venv\Scripts\pythonw.exe"" """ & appDir & "\app\server.py"" --port 4578", 0, False
Else
    shell.Run "cmd.exe /c """ & appDir & "\start_service.bat""", 0, False
End If
