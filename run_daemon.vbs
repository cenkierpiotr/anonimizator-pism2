' Uruchamia daemon anonimizacji w tle bez widocznego okna konsoli.
' Szuka instalacji aplikacji w standardowej lokalizacji, a gdy jej nie znajdzie
' - uruchamia serwer z drzewa repo, z ktorego skrypt zostal wywolany.
Option Explicit
Dim shell, fso, appDir
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programy\Anonimizator Pism"
If Not fso.FileExists(appDir & "\app\server.py") Then appDir = fso.GetParentFolderName(WScript.ScriptFullName)

shell.Run "cmd.exe /c """ & appDir & "\run_daemon.bat""", 0, False
