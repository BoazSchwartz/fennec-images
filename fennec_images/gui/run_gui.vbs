' Start Fennec Images with no console window. This is what the desktop shortcut
' (Fennec Images.lnk) points at, and double-clicking this file does the same.
'
' A .bat always opens the black console box first, whatever window style the
' shortcut asks for, so the launch goes through this .vbs: it runs the run_images.bat
' beside it with the window hidden and nothing of its own appears.
'
' The console output is not thrown away -- a start-up traceback is the only sign
' of a GUI that never opens -- it is redirected to log\launch_images.log in the repo root,
' overwritten at each launch. run_images.bat still works on its own in a console.

Option Explicit
Dim fso, sh, q, here, root, bat, dir_log, file_log, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
q = Chr(34)
here = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(fso.GetParentFolderName(here))
bat = here & "\run_images.bat"

If Not fso.FileExists(bat) Then
    MsgBox "run_images.bat not found beside this script:" & vbCrLf & bat, vbExclamation, "Fennec Images"
    WScript.Quit 1
End If

dir_log = root & "\log"
On Error Resume Next
If Not fso.FolderExists(dir_log) Then fso.CreateFolder(dir_log)
On Error GoTo 0
file_log = dir_log & "\launch_images.log"

sh.CurrentDirectory = root
' cmd /c with more than two quotes: the outer pair is stripped, the inner ones stay
cmd = "cmd.exe /c " & q & q & bat & q & " > " & q & file_log & q & " 2>&1" & q
sh.Run cmd, 0, False
WScript.Quit 0
