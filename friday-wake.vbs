' ===============================================================
'  FRIDAY Wake - autostart OCULTO al iniciar sesion en Windows.
'
'  Que hace:
'    1. Sincroniza el listener (windows_wake.py) desde el repo en WSL.
'    2. Lo arranca SIN ventana con pythonw.exe (no parpadea ninguna consola).
'
'  El listener queda escuchando "FRIDAY". Al detectarla, el solo levanta
'  Ollama + FRIDAY (API + dashboard) en WSL y abre el HUD - nada mas.
'
'  Instalacion (una vez):
'    - Win+R -> shell:startup -> Enter.
'    - Copia ESTE archivo a esa carpeta. Arranca solo en cada login.
'
'  NOTA: pythonw.exe (no py.exe) = sin consola. Si tu Python 3.12 esta en
'  otra ruta, ajusta 'pyw'. py -3.12 abriria una consola que no queremos.
' ===============================================================

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

src = "\\wsl$\Ubuntu\home\gonzalo\dev\personal\friday\friday\voice\windows_wake.py"
dst = "C:\Users\gonza\friday\windows_wake.py"

' Best-effort: si el repo en WSL esta accesible, sincroniza la ultima version.
' On Error + FileExists: si WSL todavia no monto al login, no rompe (usa la copia local).
On Error Resume Next
If fso.FileExists(src) Then fso.CopyFile src, dst, True
On Error GoTo 0

pyw = "C:\Users\gonza\AppData\Local\Programs\Python\Python312\pythonw.exe"
' 0 = ventana oculta, False = no esperar a que termine.
sh.Run """" & pyw & """ """ & dst & """", 0, False
