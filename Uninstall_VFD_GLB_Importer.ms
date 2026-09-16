/* Uninstall — V.F.D GLB Importer Created By Fady Derias
   Drag into viewport. Removes installed copies (source folder untouched). */
(
    try ( closeRolloutFloater ::GLBImporterFloater ) catch()
    try (
        deleteFile ((getDir #userMacros) + "\\VFD_GLB_Importer.mcr")
        deleteFile ((getDir #userIcons) + "\\VFDGLB_16i.bmp")
        deleteFile ((getDir #userIcons) + "\\VFDGLB_24i.bmp")
        deleteFile ((getDir #userStartupScripts) + "\\VFD_GLBImporter_Startup.ms")
        -- core (keep folder, remove files)
        deleteFile ((getDir #userScripts) + "\\VFD_GLBImporter\\GLBImporter.ms")
        deleteFile ((getDir #userScripts) + "\\VFD_GLBImporter\\glb_importer.py")
        format "V.F.D: uninstalled. Restart Max to clear menu/toolbar entries.\n"
        messageBox "V.F.D GLB Importer uninstalled.\nRestart Max to fully clear menus."
    ) catch ( messageBox ("Uninstall issue:\n" + ((getCurrentException()) as string)) )
)
