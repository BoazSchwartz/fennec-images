' Rewrite the desktop shortcut of Fennec Images -- the green F.
'
' A .bat file cannot carry an icon of its own; a shortcut can, so what sits on the desktop
' is a .lnk pointing at fennec_images\gui\run_gui.vbs (not at the .bat, which always opens
' the black console box first -- the .vbs runs the same .bat hidden).
'
' A shortcut stores absolute paths, so it is not tracked by git; the .bat rewrites it on
' every launch instead, which also heals it after the repo folder moves. A failure here
' must never stop the launch that called us.

Option Explicit
Dim fso, sh, root, desk, lnk, sep
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
desk = sh.SpecialFolders("Desktop")
sep = "\"

On Error Resume Next
Set lnk = sh.CreateShortcut(desk & sep & "Fennec Images.lnk")
lnk.TargetPath = root & sep & "fennec_images\gui\run_gui.vbs"
lnk.WorkingDirectory = root
lnk.IconLocation = root & sep & "assets\fennec-images.ico,0"
lnk.Description = "Fennec Images - classify photos and documents, build albums"
lnk.Save
WScript.Quit 0
