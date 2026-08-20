Option Explicit
Dim shell, fso, root, python, server, url, i
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

' Preferred: Hermes venv (developer machine). Fallback: python on PATH.
Dim hermesPython, defaultPython
hermesPython = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\hermes\hermes-agent\venv\Scripts\python.exe"
If fso.FileExists(hermesPython) Then
  python = hermesPython
Else
  python = "python"
End If

server = Chr(34) & root & "\captions_maker_server.py" & Chr(34)
url = "http://127.0.0.1:8770/captions-maker.html?desktop=1"

' Start backend hidden. If it is already running, the existing instance remains usable.
shell.CurrentDirectory = root
shell.Run Chr(34) & python & Chr(34) & " " & server, 0, False

' Wait briefly for the local server, then open the UI in the default browser.
For i = 1 To 30
  If IsPortOpen("127.0.0.1", 8770) Then Exit For
  WScript.Sleep 500
Next
shell.Run "cmd /c start """" """ & url & """", 0, False

Function IsPortOpen(host, port)
  Dim http
  On Error Resume Next
  Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
  http.Open "GET", "http://" & host & ":" & port & "/captions-maker.html", False
  http.Send
  IsPortOpen = (Err.Number = 0 And http.Status = 200)
  Err.Clear
End Function
