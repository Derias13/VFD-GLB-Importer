/* ============================================================
   SETUP — V.F.D GLB Importer Created By Fady Derias
   HOW TO INSTALL:
     1. Drag THIS file into the 3ds Max viewport (or Scripting > Run Script).
     2. Wait for "Installed OK" message. Done — icon is registered.
     3. (Optional) Customize > Customize User Interface > Toolbars >
        Category "V.F.D" > drag "VFD GLB" to any toolbar.
   WHAT IT DOES:
     - Copies GLBImporter.ms + glb_importer.py to
       #userScripts\VFD_GLBImporter\
     - Copies icons to #userIcons\ (VFDGLB_16i / _24i)
     - Installs VFD_GLB_Importer.mcr to #userMacros\ (the toolbar icon)
     - Writes startup loader so it survives Max restarts
     - Adds a "V.F.D" menu item under the main menu bar
     - Opens the importer window immediately
   ============================================================ */

(
    local srcDir = getFilenamePath (getThisScriptFilename())
    local dstDir = (getDir #userScripts) + "\\VFD_GLBImporter"
    local macroDir = getDir #userMacros
    local iconDir = getDir #userIcons
    local startupDir = getDir #userStartupScripts
    local ok = true

    format "V.F.D Setup: source=%\n" srcDir
    format "V.F.D Setup: target=%\n" dstDir

    -- 1. folders
    try ( makeDir dstDir all:true ) catch()

    -- 2. copy core files
    local files = #("GLBImporter.ms", "glb_importer.py")
    for fname in files do (
        local s = srcDir + fname
        local d = dstDir + "\\" + fname
        if doesFileExist s then (
            try ( copyFile s d; format "V.F.D Setup: copied % -> %\n" s d )
            catch ( format "V.F.D Setup: COPY FAILED %\n" s; ok = false )
        ) else ( format "V.F.D Setup: MISSING source %\n" s; ok = false )
    )

    -- 3. icons (optional but nice)
    for ic in #("VFDGLB_16i.bmp", "VFDGLB_24i.bmp") do (
        local s = srcDir + "icons\\" + ic
        local d = iconDir + "\\" + ic
        if doesFileExist s then (
            try ( copyFile s d; format "V.F.D Setup: icon %\n" d )
            catch ( format "V.F.D Setup: icon copy failed %\n" ic )
        ) else (
            format "V.F.D Setup: icon not found %, skipping\n" s
        )
    )

    -- 4. macroscript (toolbar icon) -> #userMacros
    try (
        local s = srcDir + "VFD_GLB_Importer.mcr"
        local d = macroDir + "\\VFD_GLB_Importer.mcr"
        if doesFileExist s then (
            copyFile s d
            format "V.F.D Setup: macro %\n" d
            -- register installed dir for the macro to find backend
            global VFDGLBInstalledDir = dstDir
            try ( persistent global VFDGLBInstalledDir ) catch()
            fileIn d  -- load macro def into session
            -- refresh macros so Customize UI sees Category "V.F.D"
            try ( macros.load (macroDir + "\\VFD_GLB_Importer.mcr") ) catch()
            try ( cui.updateToolbarGlobals() ) catch()
            try ( colorman.reInitIcons() ) catch()
        ) else ( format "V.F.D Setup: MISSING %\n" s; ok = false )
    ) catch ( format "V.F.D Setup: macro failed: %\n" (getCurrentException()); ok = false )

    -- 5. startup loader (survives restart)
    try (
        local loader = startupDir + "\\VFD_GLBImporter_Startup.ms"
        local fs = createFile loader
        format "global VFDGLBInstalledDir = @\"%\"\n" dstDir to:fs
        format "try ( fileIn (VFDGLBInstalledDir + \"\\\\GLBImporter.ms\") ) catch()\n" to:fs
        close fs
        format "V.F.D Setup: startup %\n" loader
    ) catch ( format "V.F.D Setup: startup failed: %\n" (getCurrentException()); ok = false )

    -- 6. main menu entry: Menu "V.F.D" (best effort, version-proof)
    try (
        if menuMan != undefined then (
            local mm = menuMan.getMainMenuBar()
        local sub = undefined
        try ( sub = menuMan.findMenu "V.F.D" ) catch()
        if sub == undefined then (
            sub = menuMan.createMenu "V.F.D"
            local subItem = menuMan.createSubMenuItem "V.F.D" sub
            mm.addItem subItem (mm.numItems())
            format "V.F.D Setup: menu created\n"
        )
        -- add action if not already there
        local found = false
        for i = 1 to sub.numItems() do (
            try ( if (sub.getItem i).getTitle() == "V.F.D GLB Importer" then found = true ) catch()
        )
        if not found then (
            local act = menuMan.createActionItem "VFDGLBImporter" "V.F.D"
            act.setTitle "V.F.D GLB Importer"
            act.setUseCustomTitle true
            sub.addItem act (sub.numItems() + 1)
            format "V.F.D Setup: menu item added\n"
        )
        menuMan.updateMenuBar()
        ) else (
            format "V.F.D Setup: menuMan not available, skipping menu (non-fatal)\n"
        )
    ) catch ( format "V.F.D Setup: menu skipped (non-fatal): %\n" (getCurrentException()) )

    -- 7. open it now from installed location
    try ( fileIn (dstDir + "\\GLBImporter.ms") ) catch (
        format "V.F.D Setup: open failed: %\n" (getCurrentException()); ok = false
    )

    if ok then (
        messageBox "V.F.D GLB Importer Created By Fady Derias\nInstalled OK!\n\nFind the icon at:\nCustomize > Customize User Interface > Toolbars > Category 'V.F.D' > 'VFD GLB'\nAlso in menu bar: V.F.D > V.F.D GLB Importer"
    ) else (
        messageBox "V.F.D Setup finished WITH WARNINGS.\nSee Listener (F11) for details."
    )
)
