# V.F.D GLB Importer

**Created by Fady Derias**

A one-click **glTF 2.0 / GLB importer for Autodesk 3ds Max 2024–2026**. No dependencies, no pip packages — just drag, install, and import.

![Max versions](https://img.shields.io/badge/3ds_Max-2024_|_2025_|_2026-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Features

- **Full mesh import** — `POSITION`, `NORMAL`, `TEXCOORD_0`, indexed triangles, triangle strips & fans
- **PBR materials** — `PhysicalMaterial` with base color, metallic, roughness, normal, emissive & occlusion maps, double-sided and alpha (`BLEND` / `MASK`) support
- **Embedded textures** — images stored in the GLB (or base64 / external files) are extracted automatically and wired up with correct gamma
- **Correct UVs** — mapping channel is built before conversion, so textures land where they should (V-flip optional)
- **Node hierarchy** — full scene tree, or clean **mesh-only** import with zero Dummy helpers (default)
- **Skin & animation** — basic `Skin` weights (`JOINTS_0` / `WEIGHTS_0`) and baked TRS keyframes
- **Smart units** — GLB files are always in meters; the importer auto-converts to your Max system unit (mm / cm / m / inches / feet…)
- **Normalize tool** — one field rescales unit-cube outputs (e.g. ComfyUI WhiteMesh) to any real-world size
- **Y-Up → Z-Up** conversion with proper quaternion handling

## 📋 Requirements

- Autodesk 3ds Max **2024, 2025 or 2026**
- Nothing else. The Python backend uses only the standard library + `pymxs`.

## 📦 What's in the box

| File | Purpose |
|---|---|
| `Install_VFD_GLB_Importer.ms` | **Run this once** — the setup (copies files, registers icon + menu) |
| `GLBImporter.ms` | Main UI (installed to `#userScripts\VFD_GLBImporter\`) |
| `glb_importer.py` | Import backend, dependency-free (installed alongside) |
| `VFD_GLB_Importer.mcr` | Toolbar macroscript, Category **"V.F.D"** |
| `icons\VFDGLB_16i.bmp`, `VFDGLB_24i.bmp` | Custom gold-V toolbar icon |
| `Uninstall_VFD_GLB_Importer.ms` | Clean removal |

## 🚀 Installation

1. Open 3ds Max.
2. Drag **`Install_VFD_GLB_Importer.ms`** into the viewport (or *Scripting → Run Script*).
3. Wait for **“Installed OK”** — the importer window opens by itself. Done!

The toolbar button lives at **Customize → Customize User Interface → Toolbars → Category “V.F.D” → “VFD GLB”** — drag it onto any toolbar. You'll also find it under the main menu bar: **V.F.D → V.F.D GLB Importer**. The installation survives Max restarts via a startup loader.

## 🖱️ Usage

1. Click **Browse GLB / glTF** and pick a `.glb` (or `.gltf`) file.
2. Tune the options (defaults work for most files).
3. Click **IMPORT**. Watch the Listener (**F11**) for the detailed log.

## ⚙️ Options

| Option | Default | Notes |
|---|---|---|
| Auto meters → System unit | ✅ ON | Converts GLB meters to your Max system unit automatically |
| Manual scale | 1.0 | Extra multiplier applied on top |
| Normalize longest side to (0 = off) | 0 | Rescales the whole model so its longest side equals this value (in system units). Perfect for normalized AI outputs |
| Materials (Physical) | ✅ | Uncheck for raw gray meshes |
| Textures | ✅ | Extracts & wires embedded images |
| Hierarchy | ✅ | Full node tree. Combine with the Dummy toggle below |
| Create Dummy helpers | ❌ OFF | ON = helper tree (`world`, `GLB_Root`…), OFF = clean mesh-only import |
| Animation (baked) | ✅ | Bakes TRS keyframes at the scene frame rate |
| Skin (basic) | ✅ | Adds a `Skin` modifier from joints/weights |
| Convert Y-Up to Z-Up | ✅ | glTF is Y-up, Max is Z-up |
| Flip UV-V | ✅ | Matches DirectX-style UVs to Max |

> **Tip — ComfyUI / AI meshes:** generators like ComfyUI often export a normalized 1×1×1 m cube. Set *Normalize longest side* to your target size (e.g. `2000` when working in centimeters for a 20 m building).

## 🗑️ Uninstall

Drag `Uninstall_VFD_GLB_Importer.ms` into the viewport and restart Max.

## 🕘 Version history

- **v2.0** — Branded setup release: one-click installer, custom toolbar icon, main-menu entry, startup loader, mesh-only (no-Dummy) mode, auto unit conversion, normalize tool, UV-overhaul fix
- **v1.3** — Scale & unit handling
- **v1.2** — UV mapping rewrite (build maps before Poly conversion), texture gamma + viewport display
- **v1.1** — UI auto-open fix
- **v1.0** — Initial full importer (mesh / PBR / hierarchy / skin / animation)

## ⚠️ Known limitations

- Draco-compressed meshes are skipped (extension decoder not bundled)
- `CUBICSPLINE` tangents are baked as linear; morph targets and `KHR` light/material extensions are not imported
- Skin import is basic — complex rigs may need manual cleanup
- `POINTS` / `LINES` primitives are skipped (triangles only)

## 📄 License

MIT — see [LICENSE](LICENSE). Free for commercial and personal use.

## 👤 Author

**Fady Derias** — V.F.D GLB Importer
