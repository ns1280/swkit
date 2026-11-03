Option Explicit
On Error Resume Next

' 通用单件生成器：按 .job 文件建一个 SLDPRT。
' 草图一律在右视面（Y-Z），u=-z、v=y，拉伸沿 X；作业文件单位为米。
' 用法：cscript //nologo build_part.vbs <job文件>
' 作业格式（制表符分隔）：
'   OUT <零件路径> / PREVIEW <bmp路径> / TEMPLATE <prtdot 路径，可选>
'   FEAT <名> → LINE y1 z1 y2 z2 | ARC cy cz sy sz ey ez dir | CIRCLE cy cz r
'   EXTRUDE <depth> <start> <merge 0|1>

Dim TEMPLATE
TEMPLATE = "C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_part.prtdot"
If WScript.Arguments.Count > 1 Then TEMPLATE = WScript.Arguments(1)

Dim fso, jobPath, jobFile, logFile, outPath, previewPath
Dim sw, model, sk, body, line, a

Set fso = CreateObject("Scripting.FileSystemObject")
jobPath = WScript.Arguments(0)
Set logFile = fso.CreateTextFile(jobPath & ".log", True, True)

Sub Lg(s)
    logFile.WriteLine s
End Sub

Sub Fail(s)
    Lg "error=" & s
    Lg "success=false"
    logFile.Close
    WScript.Echo "ERROR: " & s
    WScript.Quit 1
End Sub

Function Num(s)
    Num = CDbl(s)
End Function

Set jobFile = fso.OpenTextFile(jobPath, 1, False, 0)
Set sw = CreateObject("SldWorks.Application")
sw.Visible = True
Set model = sw.NewDocument(TEMPLATE, 0, 0, 0)
If model Is Nothing Then Fail "NewDocument"
Lg "doc=" & model.GetTitle()
Lg "sw_version=" & sw.RevisionNumber()

Sub SelectPlane(idx)
    Dim f, n
    Set f = model.FirstFeature()
    n = 0
    Do While Not (f Is Nothing)
        If f.GetTypeName2() = "RefPlane" Then
            n = n + 1
            If n = idx Then Exit Do
        End If
        Set f = f.GetNextFeature()
    Loop
    If f Is Nothing Then Fail "plane " & idx
    f.Select2 False, 0
End Sub

Sub StartSketch()
    model.ClearSelection2 True
    SelectPlane 3
    model.SketchManager.InsertSketch True
    Set sk = model.SketchManager.ActiveSketch
    If sk Is Nothing Then Fail "sketch"
    model.SketchManager.AddToDB = True
End Sub

Sub FinishExtrude(depth, start, merge)
    Dim f, last
    model.SketchManager.AddToDB = False
    model.SketchManager.InsertSketch True
    model.ClearSelection2 True
    Set f = model.FirstFeature()
    Set last = Nothing
    Do While Not (f Is Nothing)
        Set last = f
        Set f = f.GetNextFeature()
    Loop
    If last Is Nothing Then Fail "no last feature"
    If Not last.Select2(False, 0) Then Fail "select last feature"
    Err.Clear
    Set body = model.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, depth, 0.0, _
        False, False, False, False, 0.0, 0.0, False, False, False, False, _
        merge, merge, merge, 3, start, False)
    If Err.Number <> 0 Then Fail "extrude " & Err.Number & " " & Err.Description
    If IsNull(body) Then Fail "extrude returned null"
End Sub

Do While Not jobFile.AtEndOfStream
    line = Trim(jobFile.ReadLine())
    If Len(line) > 0 Then
        a = Split(line, vbTab)
        Select Case a(0)
            Case "OUT"
                outPath = a(1)
            Case "PREVIEW"
                previewPath = a(1)
            Case "TEMPLATE"
                ' 模板已由命令行参数传入；这一行只作为作业记录保留
            Case "FEAT"
                StartSketch
            Case "LINE"
                model.SketchManager.CreateLine -Num(a(2)), Num(a(1)), 0, -Num(a(4)), Num(a(3)), 0
            Case "ARC"
                model.SketchManager.CreateArc -Num(a(2)), Num(a(1)), 0, _
                    -Num(a(4)), Num(a(3)), 0, -Num(a(6)), Num(a(5)), 0, CInt(a(7))
            Case "CIRCLE"
                model.SketchManager.CreateCircleByRadius -Num(a(2)), Num(a(1)), 0, Num(a(3))
            Case "EXTRUDE"
                FinishExtrude Num(a(1)), Num(a(2)), (CInt(a(3)) = 1)
                If Err.Number <> 0 Then Fail "after extrude " & Err.Description
            Case Else
                Fail "unknown command " & a(0)
        End Select
        If Err.Number <> 0 Then Fail "at " & a(0) & ": " & Err.Number & " " & Err.Description
    End If
Loop
jobFile.Close

model.EditRebuild3
Err.Clear
model.SaveAs3 outPath, 0, 0
If Err.Number <> 0 Then Fail "SaveAs3 " & Err.Description
If Not fso.FileExists(outPath) Then Fail "file missing"
Lg "saved_bytes=" & fso.GetFile(outPath).Size

sw.CloseDoc outPath
Set model = sw.OpenDoc(outPath, 1)
If model Is Nothing Then Fail "reopen"
Dim bodies, cnt
bodies = model.GetBodies2(0, True)
cnt = 0
If IsArray(bodies) Then
    On Error Resume Next
    cnt = UBound(bodies) - LBound(bodies) + 1
End If
Lg "solid_bodies=" & cnt
model.ShowNamedView2 "", 7
model.ViewZoomtofit2
model.ViewDisplayShaded
model.SaveBMP previewPath, 1200, 900
Lg "preview=" & fso.FileExists(previewPath)
sw.CloseDoc outPath
Lg "success=true"
logFile.Close
WScript.Echo "OK " & outPath & " bodies=" & cnt
WScript.Quit 0
