/* ============================================================
   V.F.D GLB Importer Created By Fady Derias — v2.0 (setup ready)
   Backend: glb_importer.py (same folder)
   Install: run Install_VFD_GLB_Importer.ms once (drag into viewport).
   Manual: Scripting > Run Script > this file -> window opens auto.
   ============================================================ */

global GLBImporterFloater = undefined
global GLBImporterPy = undefined
global GLBImporterSelFile = undefined

fn GLBImporterFindPy = (
    local thisPath = ""
    try ( thisPath = getThisScriptFilename() ) catch ( thisPath = "" )
    local dir = ""
    try ( dir = getFilenamePath thisPath ) catch ( dir = "" )
    local candidates = #()
    if dir != "" then append candidates (dir + "glb_importer.py")
    append candidates ((getDir #userScripts) + "\\glb_importer.py")
    append candidates ((getDir #maxroot) + "\\scripts\\glb_importer.py")
    for c in candidates do ( if doesFileExist c then return c )
    return undefined
)

fn GLBImporterEnsurePy = (
    if GLBImporterPy == undefined or not doesFileExist GLBImporterPy then
        GLBImporterPy = GLBImporterFindPy()
    if GLBImporterPy == undefined then (
        messageBox "glb_importer.py not found!\nPut it in the SAME folder as GLBImporter.ms"
        format "GLBImporter: glb_importer.py NOT FOUND\n"
        return false
    )
    format "GLBImporter: loading backend %\n" GLBImporterPy
    try (
        python.executeFile GLBImporterPy
        return true
    ) catch (
        messageBox ("Python backend failed:\n" + (getCurrentException() as string))
        return false
    )
)

fn GLBImporterDoImport filepath optScale optUp optMat optTex optHier optAnim optSkin optFlipV optAutoUnit optTarget optDummy = (
    if not GLBImporterEnsurePy() then return false
    local esc = substituteString filepath "\\" "\\\\"
    esc = substituteString esc "'" "\\'"
    local cmd = "GLB_IMPORT('" + esc + "', scale=" + (optScale as string) \
        + ", convert_up=" + (if optUp then "True" else "False") \
        + ", import_materials=" + (if optMat then "True" else "False") \
        + ", import_textures=" + (if optTex then "True" else "False") \
        + ", import_hierarchy=" + (if optHier then "True" else "False") \
        + ", import_animation=" + (if optAnim then "True" else "False") \
        + ", import_skin=" + (if optSkin then "True" else "False") \
        + ", flip_uv_v=" + (if optFlipV then "True" else "False") \
        + ", auto_unit=" + (if optAutoUnit then "True" else "False") \
        + ", target_size=" + (optTarget as string) \
        + ", create_dummies=" + (if optDummy then "True" else "False") + ")"
    format "GLBImporter: importing %\n" filepath
    format "GLBImporter: system unit is % (display: %)\n" units.SystemType units.DisplayType
    local t0 = timestamp()
    try (
        undo "Import GLB" on (
            with redraw off (
                python.execute cmd
            )
        )
        format "GLBImporter: done in % sec\n" ((timestamp() - t0) / 1000.0)
        messageBox "GLB import done. Check Listener (F11) for details."
        return true
    ) catch (
        local err = getCurrentException()
        format "GLBImporter FAILED: %\n" err
        messageBox ("GLB import failed:\n" + (err as string))
        return false
    )
)

-- NOTE: rollout MUST be top-level, not inside a function
rollout GLBImpRoll "V.F.D GLB Importer - Created By Fady Derias" width:320
(
    edittext edtPath "" fieldWidth:290 height:22 readOnly:true text:"No file selected..."
    button btnBrowse "Browse GLB / glTF..." width:290 height:28
    group "Scale (GLB is always meters)" (
        checkbox chkAuto "Auto meters -> System unit" checked:true
        spinner spnScale "Manual x:" range:[0.0001,100000,1.0] type:#float scale:0.01 fieldWidth:80
        spinner spnTarget "Normalize longest side to (0=off):" range:[0,100000,0] type:#float scale:1.0 fieldWidth:80
        label lblHint "ComfyUI WhiteMesh = 1m cube. Set Normalize=2000 for 20m church in cm."
    )
    group "Options" (
        checkbox chkMat "Materials (Physical)" checked:true
        checkbox chkTex "Textures" checked:true
        checkbox chkHier "Hierarchy" checked:true
        checkbox chkDummy "Create Dummy helpers (OFF=mesh only)" checked:false
        checkbox chkAnim "Animation (baked)" checked:true
        checkbox chkSkin "Skin (basic)" checked:true
        checkbox chkUp "Convert Y-Up to Z-Up" checked:true
        checkbox chkFlipV "Flip UV-V" checked:true
    )
    button btnImport "IMPORT" width:290 height:36 enabled:false

    on btnBrowse pressed do (
        local f = getOpenFileName caption:"Select GLB / glTF" \
            types:"GLB (*.glb)|*.glb|glTF (*.gltf)|*.gltf|All|*.*"
        if f != undefined then (
            ::GLBImporterSelFile = f
            edtPath.text = f
            btnImport.enabled = true
            format "GLBImporter selected: %\n" f
        )
    )
    on btnImport pressed do (
        if ::GLBImporterSelFile == undefined then (
            messageBox "Select a file first."
        ) else (
            ::GLBImporterDoImport ::GLBImporterSelFile spnScale.value \
                chkUp.checked chkMat.checked chkTex.checked chkHier.checked \
                chkAnim.checked chkSkin.checked chkFlipV.checked \
                chkAuto.checked spnTarget.value chkDummy.checked
        )
    )
)

fn GLBImporterOpen = (
    if GLBImporterFloater != undefined then (
        try ( closeRolloutFloater GLBImporterFloater ) catch()
        GLBImporterFloater = undefined
    )
    GLBImporterFloater = newRolloutFloater "V.F.D GLB Importer - Created By Fady Derias" 340 540
    addRollout GLBImpRoll GLBImporterFloater
    format "GLBImporter: window opened. System=% Display=%\n" units.SystemType units.DisplayType
    return true
)

macroScript VFDGLBImporter
    category:"V.F.D"
    toolTip:"V.F.D GLB Importer Created By Fady Derias"
    buttonText:"VFD GLB"
    icon:#("VFDGLB",1)
(
    on execute do ( try ( ::GLBImporterOpen() ) catch() )
)

utility GLBImporterUtil "V.F.D GLB Importer"
(
    button btnOpenUI "Open GLB Importer..." width:150 height:30
    label lbl1 "GLB/glTF 2.0 import"
    label lbl2 "Max 2024-2026"
    on btnOpenUI pressed do ( ::GLBImporterOpen() )
)

format "V.F.D GLB Importer Created By Fady Derias v2.0 loaded OK. Opening window...\n"
try ( GLBImporterOpen() ) catch ( format "GLBImporter: auto-open failed: %\n" (getCurrentException()) )
