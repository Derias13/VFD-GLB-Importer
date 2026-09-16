/* V.F.D GLB Importer Created By Fady Derias — toolbar macroscript
   Placed automatically into #userMacros by the installer.
   Category "V.F.D" -> drag it to any toolbar from Customize UI. */
macroScript VFDGLBImporter
    category:"V.F.D"
    toolTip:"V.F.D GLB Importer Created By Fady Derias"
    buttonText:"VFD GLB"
    icon:#("VFDGLB",1)
(
    global VFDGLBInstalledDir
    on execute do
    (
        local main = undefined
        try ( main = VFDGLBInstalledDir + "\\GLBImporter.ms" ) catch()
        if main != undefined and doesFileExist main then
            fileIn main
        else (
            -- fallback: already-loaded session function
            try ( ::GLBImporterOpen() ) catch (
                messageBox "V.F.D GLB Importer not found. Run Install_VFD_GLB_Importer.ms first."
            )
        )
    )
)
