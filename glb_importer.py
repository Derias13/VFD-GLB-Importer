"""
GLB / glTF 2.0 Importer for 3ds Max 2024-2026
No external dependencies. Pure Python + pymxs.
Supports: meshes, PBR materials, textures, hierarchy, skins (basic), animations (baked).

Called from MAXScript:
    python.executeFile <path to this file>
    python.execute "GLB_IMPORT(r'c:\\model.glb', {...})"
"""

import struct
import json
import os
import base64
import math
import tempfile
import traceback

COMP_BYTE = 5120
COMP_UBYTE = 5121
COMP_SHORT = 5122
COMP_USHORT = 5123
COMP_UINT = 5125
COMP_FLOAT = 5126

COMP_FMT = {
    COMP_BYTE: ('b', 1),
    COMP_UBYTE: ('B', 1),
    COMP_SHORT: ('h', 2),
    COMP_USHORT: ('H', 2),
    COMP_UINT: ('I', 4),
    COMP_FLOAT: ('f', 4),
}

TYPE_COUNT = {
    'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4,
    'MAT2': 4, 'MAT3': 9, 'MAT4': 16,
}

PRIM_POINTS = 0
PRIM_LINES = 1
PRIM_LINE_LOOP = 2
PRIM_LINE_STRIP = 3
PRIM_TRIANGLES = 4
PRIM_TRI_STRIP = 5
PRIM_TRI_FAN = 6


# ---------------------------------------------------------------- parsing

def _read_glb(path):
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 12:
        raise ValueError('File too small, not a GLB')
    magic, version, length = struct.unpack('<III', data[:12])
    if magic != 0x46546C67:  # 'glTF'
        raise ValueError('Not a GLB file (bad magic)')
    if version != 2:
        raise ValueError('Only glTF 2.0 supported, got version %d' % version)
    offset = 12
    json_dict = None
    bin_chunk = b''
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack('<II', data[offset:offset + 8])
        offset += 8
        chunk = data[offset:offset + chunk_len]
        offset += chunk_len
        if chunk_type == 0x4E4F534A:  # JSON
            json_dict = json.loads(chunk.decode('utf-8'))
        elif chunk_type == 0x004E4942:  # BIN
            bin_chunk = chunk
    if json_dict is None:
        raise ValueError('GLB has no JSON chunk')
    return json_dict, bin_chunk


def _read_gltf(path):
    with open(path, 'r', encoding='utf-8') as f:
        j = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    buffers = []
    for b in j.get('buffers', []):
        uri = b.get('uri', '')
        if uri.startswith('data:'):
            # data:application/octet-stream;base64,....
            _, b64 = uri.split(',', 1)
            buffers.append(base64.b64decode(b64))
        elif uri == '' or uri is None:
            buffers.append(b'')
        else:
            with open(os.path.join(base, uri), 'rb') as f2:
                buffers.append(f2.read())
    return j, buffers, base


class GLTFDoc(object):
    def __init__(self, js, bins, base_dir=''):
        self.js = js
        self.bins = bins  # list of bytes, bins[0] is GLB BIN
        self.base_dir = base_dir
        self._img_files = []  # temp files to keep

    def get_buffer(self, idx):
        if idx < len(self.bins):
            return self.bins[idx]
        return b''

    def read_buffer_view(self, bv_idx):
        bv = self.js['bufferViews'][bv_idx]
        buf = self.get_buffer(bv.get('buffer', 0))
        off = bv.get('byteOffset', 0)
        ln = bv['byteLength']
        return buf[off:off + ln]

    def accessor_data(self, acc_idx):
        acc = self.js['accessors'][acc_idx]
        comp = acc['componentType']
        typ = acc['type']
        count = acc['count']
        ncomp = TYPE_COUNT[typ]
        fmt_char, sz = COMP_FMT[comp]
        bv_idx = acc.get('bufferView', None)
        if bv_idx is None:
            return [0.0] * (count * ncomp)  # sparse / empty
        bv = self.js['bufferViews'][bv_idx]
        buf = self.get_buffer(bv.get('buffer', 0))
        voff = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
        stride = bv.get('byteStride', 0)
        out = []
        if stride and stride != ncomp * sz:
            for i in range(count):
                o = voff + i * stride
                vals = struct.unpack('<' + fmt_char * ncomp, buf[o:o + ncomp * sz])
                out.extend(vals)
        else:
            total = count * ncomp
            vals = struct.unpack('<' + fmt_char * total, buf[voff:voff + total * sz])
            out = list(vals)
        # normalize?
        normalized = acc.get('normalized', False)
        if normalized:
            out = [self._denorm(v, comp) for v in out]
        return out

    @staticmethod
    def _denorm(v, comp):
        if comp == COMP_BYTE:
            return max(v / 127.0, -1.0)
        if comp == COMP_UBYTE:
            return v / 255.0
        if comp == COMP_SHORT:
            return max(v / 32767.0, -1.0)
        if comp == COMP_USHORT:
            return v / 65535.0
        return float(v)

    def image_to_file(self, img_idx, tmpdir):
        imgs = self.js.get('images', [])
        img = imgs[img_idx]
        mime = img.get('mimeType', '')
        ext = '.png'
        if 'jpeg' in mime or 'jpg' in mime:
            ext = '.jpg'
        elif 'webp' in mime:
            ext = '.webp'
        elif 'ktx' in mime:
            ext = '.ktx2'
        name = img.get('name', 'img%d' % img_idx).replace(' ', '_')
        # sanitize
        name = ''.join(c if (c.isalnum() or c in '_-') else '_' for c in name)[:40]
        out_path = os.path.join(tmpdir, '%s_%d%s' % (name, img_idx, ext))
        if 'bufferView' in img:
            raw = self.read_buffer_view(img['bufferView'])
            with open(out_path, 'wb') as f:
                f.write(raw)
        elif 'uri' in img:
            uri = img['uri']
            if uri.startswith('data:'):
                _, b64 = uri.split(',', 1)
                with open(out_path, 'wb') as f:
                    f.write(base64.b64decode(b64))
            else:
                src = os.path.join(self.base_dir, uri)
                # copy to tmpdir for consistent path
                try:
                    with open(src, 'rb') as fi, open(out_path, 'wb') as fo:
                        fo.write(fi.read())
                except OSError:
                    return None
                # fix ext from uri
                _, e2 = os.path.splitext(uri)
                if e2:
                    out2 = os.path.splitext(out_path)[0] + e2
                    try:
                        os.rename(out_path, out2)
                        out_path = out2
                    except OSError:
                        pass
        else:
            return None
        self._img_files.append(out_path)
        return out_path


# ---------------------------------------------------------------- math helpers (pure python)

def q_normalize(q):
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return (x / n, y / n, z / n, w / n)


def q_to_max_quat(q, convert):
    """glTF quat (x,y,z,w) -> Max quat. convert=True applies Y-up to Z-up."""
    x, y, z, w = q_normalize(q)
    if convert:
        # C * q : rotate -90 about X. Equivalent mapping on quat:
        # (x,y,z,w) -> (x, z, -y, w)? verify: vector (0,1,0) rotated by C(-90X) -> (0,0,1)
        # quat for C is ( -sin45,0,0,cos45 ). q' = C*q*C? No - for vectors we do C*v.
        # For rotations: R' = C*R*C^-1. Doing full quat multiply is safest.
        cx, cy, cz, cw = (-0.7071067811865476, 0.0, 0.0, 0.7071067811865476)
        # q' = C * q * Cinv ; Cinv = (0.7071,0,0,0.7071)
        q2 = q_mul((cx, cy, cz, cw), (x, y, z, w))
        q3 = q_mul(q2, (0.7071067811865476, 0.0, 0.0, 0.7071067811865476))
        return q_normalize(q3)
    return (x, y, z, w)


def q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def convert_pos(p, convert):
    x, y, z = p
    if convert:
        return (x, -z, y)
    return (x, y, z)


def convert_scale(s, convert):
    # scale is axis-aligned in local space; under C*R*C^-1 the components permute y<->z
    sx, sy, sz = s
    if convert:
        return (sx, sz, sy)
    return (sx, sy, sz)


def decompose_matrix16(m, convert):
    """m: 16 floats column-major. Returns (T, Q, S)."""
    # columns: X axis = m[0:3], Y = m[4:7], Z = m[8:11], T = m[12:15]
    tx, ty, tz = m[12], m[13], m[14]
    xa = (m[0], m[1], m[2])
    ya = (m[4], m[5], m[6])
    za = (m[8], m[9], m[10])
    sx = math.sqrt(sum(c * c for c in xa))
    sy = math.sqrt(sum(c * c for c in ya))
    sz = math.sqrt(sum(c * c for c in za))
    if sx < 1e-12 or sy < 1e-12 or sz < 1e-12:
        return ((tx, ty, tz), (0, 0, 0, 1), (1, 1, 1))
    # rotation matrix normalized
    rx = [c / sx for c in xa]
    ry = [c / sy for c in ya]
    rz = [c / sz for c in za]
    q = mat3_to_quat(rx, ry, rz)
    T = convert_pos((tx, ty, tz), convert)
    S = convert_scale((sx, sy, sz), convert)
    Q = q_to_max_quat(q, convert)
    return (T, Q, S)


def mat3_to_quat(rx, ry, rz):
    # columns rx,ry,rz -> row-major m
    m00, m01, m02 = rx[0], ry[0], rz[0]
    m10, m11, m12 = rx[1], ry[1], rz[1]
    m20, m21, m22 = rx[2], ry[2], rz[2]
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    return q_normalize((x, y, z, w))


def triangulate_strip(indices):
    faces = []
    for i in range(len(indices) - 2):
        a, b, c = indices[i], indices[i + 1], indices[i + 2]
        if a == b or b == c or a == c:
            continue
        if i % 2 == 0:
            faces.append((a, b, c))
        else:
            faces.append((b, a, c))
    return faces


def triangulate_fan(indices):
    faces = []
    for i in range(1, len(indices) - 1):
        faces.append((indices[0], indices[i], indices[i + 1]))
    return faces


# ---------------------------------------------------------------- Max builder

def _log(msg):
    try:
        from pymxs import runtime as rt
        rt.format("%%\n", str(msg))
    except Exception:
        print(msg)


def import_glb_file(path, opts):
    """Main entry. opts: dict with keys:
    scale, convert_up(bool), import_materials, import_textures,
    import_hierarchy, import_animation, import_skin, flip_uv_v(bool, default True)
    Returns dict summary.
    """
    from pymxs import runtime as rt

    scale = float(opts.get('scale', 1.0))
    convert = bool(opts.get('convert_up', True))
    auto_unit = bool(opts.get('auto_unit', True))
    target_size = float(opts.get('target_size', 0.0))  # 0 = off; else normalize bbox to this (in system units)
    do_mats = bool(opts.get('import_materials', True))
    do_tex = bool(opts.get('import_textures', True))
    do_hier = bool(opts.get('import_hierarchy', True))
    do_anim = bool(opts.get('import_animation', True))
    do_skin = bool(opts.get('import_skin', True))
    flip_v = bool(opts.get('flip_uv_v', True))
    create_dummies = bool(opts.get('create_dummies', False))  # user asked: no helpers by default

    # --- units: GLB is always meters. Detect Max system unit. ---
    unit_factor = 1.0
    try:
        st = str(rt.units.SystemType).lower()  # e.g. #centimeters
        if 'millimeter' in st:
            unit_factor = 1000.0
        elif 'centimeter' in st or 'centimetre' in st:
            unit_factor = 100.0
        elif 'meter' in st:
            unit_factor = 1.0
        elif 'kilometer' in st or 'kilometre' in st:
            unit_factor = 0.001
        elif 'inch' in st:
            unit_factor = 39.3701
        elif 'feet' in st or 'foot' in st:
            unit_factor = 3.28084
        elif 'mile' in st:
            unit_factor = 0.000621371
        _log('System unit: %s -> factor x%s' % (st, unit_factor))
    except Exception as e:
        _log('Unit detect failed, assuming meters: %s' % e)
    if auto_unit:
        scale = scale * unit_factor
    _log('Effective scale (incl. units): %s' % scale)

    ext = os.path.splitext(path)[1].lower()
    if ext == '.gltf':
        js, bins, base = _read_gltf(path)
        doc = GLTFDoc(js, bins, base)
    else:
        js, bin0 = _read_glb(path)
        doc = GLTFDoc(js, [bin0], os.path.dirname(os.path.abspath(path)))

    tmpdir = tempfile.mkdtemp(prefix='max_glb_')
    created_meshes = []
    created_nodes = {}   # node idx -> INode
    node_local = {}      # node idx -> (T,Q,S)
    mat_cache = {}

    def node_trs(n):
        if 'matrix' in n:
            return decompose_matrix16(n['matrix'], convert)
        t = n.get('translation', [0, 0, 0])
        r = n.get('rotation', [0, 0, 0, 1])
        s = n.get('scale', [1, 1, 1])
        T = convert_pos(t, convert)
        Q = q_to_max_quat(r, convert)
        S = convert_scale(s, convert)
        return (T, Q, S)

    # ---- materials ----
    def get_or_make_material(mi):
        if mi in mat_cache:
            return mat_cache[mi]
        mats = js.get('materials', [])
        mdef = mats[mi] if mi < len(mats) else {}
        name = mdef.get('name', 'GLB_Mat_%d' % mi)
        pbr = mdef.get('pbrMetallicRoughness', {})
        base_col = pbr.get('baseColorFactor', [1, 1, 1, 1])
        metallic = float(pbr.get('metallicFactor', 1.0))
        rough = float(pbr.get('roughnessFactor', 1.0))
        emiss = mdef.get('emissiveFactor', [0, 0, 0])
        double = bool(mdef.get('doubleSided', False))
        alpha_mode = mdef.get('alphaMode', 'OPAQUE')

        mat = rt.PhysicalMaterial()
        mat.name = name
        try:
            mat.base_color = rt.Color(
                max(0, min(255, int(base_col[0] * 255))),
                max(0, min(255, int(base_col[1] * 255))),
                max(0, min(255, int(base_col[2] * 255))))
            mat.metalness = max(0.0, min(1.0, metallic))
            mat.roughness = max(0.0, min(1.0, rough))
            if len(emiss) >= 3 and any(emiss):
                mat.emissive_color = rt.Color(
                    max(0, min(255, int(emiss[0] * 255))),
                    max(0, min(255, int(emiss[1] * 255))),
                    max(0, min(255, int(emiss[2] * 255))))
                try:
                    mat.emissive_on = True
                except Exception:
                    pass
            if double:
                try:
                    mat.double_sided = True
                except Exception:
                    pass
            if alpha_mode in ('BLEND', 'MASK'):
                try:
                    mat.transparency = 1.0 - float(base_col[3]) if len(base_col) > 3 else 0.5
                except Exception:
                    pass
        except Exception as e:
            _log('Material base props failed: %s' % e)

        def _mk_bitmap(f, map_name):
            # normalize path for Max, force reload
            fp = os.path.abspath(f).replace('\\', '/')
            bm = rt.BitmapTexture()
            bm.name = map_name
            try:
                bm.filename = fp
            except Exception:
                try:
                    bm.fileName = fp
                except Exception:
                    pass
            # color-space: albedo = sRGB, data maps = linear
            try:
                if '_BaseColor' in map_name or '_Emissive' in map_name:
                    bm.gamma = 2.2
                else:
                    bm.gamma = 1.0
            except Exception:
                pass
            try:
                bm.reload()
            except Exception:
                pass
            _log('texture saved: %s' % fp)
            return bm

        if do_tex:
            try:
                texs = js.get('textures', [])
                # base color
                bct = pbr.get('baseColorTexture', None)
                if bct is not None:
                    f = texture_file(bct.get('index', 0), tmpdir)
                    if f:
                        bm = _mk_bitmap(f, name + '_BaseColor')
                        mat.base_color_map = bm
                        try:
                            mat.base_color_map_on = True
                        except Exception:
                            pass
                mr = pbr.get('metallicRoughnessTexture', None)
                if mr is not None:
                    f = texture_file(mr.get('index', 0), tmpdir)
                    if f:
                        bm = _mk_bitmap(f, name + '_MR')
                        mat.roughness_map = bm
                nt = mdef.get('normalTexture', None)
                if nt is not None:
                    f = texture_file(nt.get('index', 0), tmpdir)
                    if f:
                        bm = _mk_bitmap(f, name + '_Normal')
                        nb = rt.Normal_Bump()
                        try:
                            nb.normal_map = bm
                        except Exception:
                            pass
                        mat.bump_map = nb
                et = mdef.get('emissiveTexture', None)
                if et is not None:
                    f = texture_file(et.get('index', 0), tmpdir)
                    if f:
                        bm = _mk_bitmap(f, name + '_Emissive')
                        mat.emissive_color_map = bm
                ot = mdef.get('occlusionTexture', None)
                if ot is not None:
                    f = texture_file(ot.get('index', 0), tmpdir)
                    if f:
                        bm = _mk_bitmap(f, name + '_AO')
                        try:
                            mat.ambient_occlusion_map = bm
                        except Exception:
                            pass
            except Exception as e:
                _log('Texture wiring failed for %s: %s' % (name, e))
        mat_cache[mi] = mat
        return mat

    def texture_file(tex_idx, tmp):
        try:
            texs = js.get('textures', [])
            if tex_idx < 0 or tex_idx >= len(texs):
                return None
            t = texs[tex_idx]
            src = t.get('source', t.get('images', 0))
            if isinstance(src, dict):
                src = 0
            return doc.image_to_file(int(src), tmp)
        except Exception:
            return None

    # ---- mesh creation ----
    def build_primitive(node_name, prim, pi):
        mode = prim.get('mode', PRIM_TRIANGLES)
        if mode not in (PRIM_TRIANGLES, PRIM_TRI_STRIP, PRIM_TRI_FAN):
            _log('Skipping non-triangle primitive mode %s' % mode)
            return None
        attrs = prim.get('attributes', {})
        if 'POSITION' not in attrs:
            return None
        pos = doc.accessor_data(attrs['POSITION'])
        nrm = doc.accessor_data(attrs['NORMAL']) if 'NORMAL' in attrs else None
        uv = doc.accessor_data(attrs['TEXCOORD_0']) if 'TEXCOORD_0' in attrs else None
        nv = len(pos) // 3
        if nv < 3:
            return None
        if 'indices' in prim:
            idx = [int(v) for v in doc.accessor_data(prim['indices'])]
        else:
            idx = list(range(nv))
        if mode == PRIM_TRI_STRIP:
            tris = triangulate_strip(idx)
        elif mode == PRIM_TRI_FAN:
            tris = triangulate_fan(idx)
        else:
            tris = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx) - 2, 3)]
        tris = [(a, b, c) for (a, b, c) in tris
                if a != b and b != c and a != c and max(a, b, c) < nv]
        if not tris:
            return None

        # convert positions
        pts = []
        for i in range(nv):
            x, y, z = pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]
            cx, cy, cz = convert_pos((x, y, z), convert)
            pts.append(rt.Point3(cx * scale, cy * scale, cz * scale))
        faces = [rt.Point3(a + 1, b + 1, c + 1) for (a, b, c) in tris]

        mesh = rt.mesh(vertices=pts, faces=faces)
        mesh.name = '%s_p%d' % (node_name[:50], pi)
        # NOTE: keep as Editable Mesh while setting UVs/normals.
        # Converting to Poly FIRST breaks meshop (was the v1.1 UV bug).

        # UVs (must run BEFORE convertTo Poly)
        if uv is not None:
            try:
                nuv = len(uv) // 2
                if nuv >= nv:
                    # Editable Mesh map API
                    try:
                        rt.setNumTVerts(mesh, nv, True)
                    except Exception:
                        pass
                    try:
                        rt.meshop.setNumMaps(mesh, 2, keep=True)
                    except Exception:
                        pass
                    try:
                        rt.meshop.setMapSupport(mesh, 1, True)
                    except Exception:
                        pass
                    ok_uv = True
                    for i in range(nv):
                        u = float(uv[i * 2])
                        v = float(uv[i * 2 + 1])
                        if flip_v:
                            v = 1.0 - v
                        try:
                            rt.meshop.setMapVert(mesh, 1, i + 1, rt.Point3(u, v, 0))
                        except Exception:
                            ok_uv = False
                            break
                    if ok_uv:
                        try:
                            # buildTVFaces replaces map faces with regular faces
                            rt.buildTVFaces(mesh, False)
                        except Exception:
                            pass
                        for fi, (a, b, c) in enumerate(tris):
                            try:
                                rt.setTVFace(mesh, fi + 1, a + 1, b + 1, c + 1)
                            except Exception:
                                try:
                                    rt.meshop.setMapFace(mesh, 1, fi + 1, rt.Point3(a + 1, b + 1, c + 1))
                                except Exception:
                                    break
                    try:
                        rt.update(mesh)
                    except Exception:
                        pass
                else:
                    _log('UV count mismatch on %s: %d vs %d verts' % (mesh.name, nuv, nv))
            except Exception as e:
                _log('UV build failed on %s: %s' % (mesh.name, e))

        # smoothing: all smooth (still Editable Mesh here)
        try:
            nf = len(tris)
            for fi in range(1, nf + 1):
                try:
                    rt.setFaceSmoothGroup(mesh, fi, 1)
                except Exception:
                    break
        except Exception:
            pass

        # material (assign while Mesh, then convert preserves it)
        if do_mats and 'material' in prim:
            try:
                m = get_or_make_material(int(prim['material']))
                mesh.material = m
                # force viewport display of base color map
                try:
                    if do_tex and hasattr(m, 'base_color_map') and m.base_color_map is not None:
                        rt.showTextureMap(m, m.base_color_map, True)
                except Exception:
                    pass
            except Exception as e:
                _log('Material assign failed: %s' % e)

        # convert to Poly ONLY at the end (preserves UVs/material)
        try:
            rt.convertTo(mesh, rt.Editable_Poly)
        except Exception:
            pass

        created_meshes.append(mesh)
        return mesh

    # ---- hierarchy ----
    nodes = js.get('nodes', [])
    meshes = js.get('meshes', [])
    skins = js.get('skins', [])

    for ni, n in enumerate(nodes):
        node_local[ni] = node_trs(n)

    # find roots
    children_sets = set()
    for n in nodes:
        for c in n.get('children', []):
            children_sets.add(c)
    roots = [i for i in range(len(nodes)) if i not in children_sets]
    if not nodes:
        roots = []
    scenes = js.get('scenes', [])
    if scenes and 'nodes' in scenes[js.get('scene', 0)]:
        roots = list(scenes[js.get('scene', 0)]['nodes'])

    def make_node_obj(ni, parent):
        n = nodes[ni]
        nm = n.get('name', 'Node_%d' % ni) or ('Node_%d' % ni)
        T, Q, S = node_local[ni]
        # does node own a mesh? meshes built as children, node itself is dummy unless leaf mesh
        has_mesh = 'mesh' in n
        if has_mesh and (not do_hier):
            # flat: mesh objects at root level with world transform baked later
            obj = rt.Dummy()
            obj.name = nm
        elif has_mesh and not n.get('children', []) and parent is not None:
            # leaf mesh node: still create dummy? No - mesh objects parented to parent directly
            obj = rt.Dummy()
            obj.name = nm
        else:
            obj = rt.Dummy()
            obj.name = nm
            try:
                obj.boxsize = rt.Point3(5 * scale, 5 * scale, 5 * scale)
            except Exception:
                pass
        if parent is not None:
            obj.parent = parent
        try:
            obj.position = rt.Point3(T[0] * scale, T[1] * scale, T[2] * scale)
            # Max quat: rt.quat x y z w
            obj.rotation = rt.quat(Q[0], Q[1], Q[2], Q[3])
            obj.scale = rt.Point3(S[0], S[1], S[2])
        except Exception as e:
            _log('Transform set failed on %s: %s' % (nm, e))
        created_nodes[ni] = obj
        # build own meshes
        if has_mesh:
            mi = int(n['mesh'])
            if 0 <= mi < len(meshes):
                mdef = meshes[mi]
                for pi, prim in enumerate(mdef.get('primitives', [])):
                    m = build_primitive(nm, prim, pi)
                    if m is not None:
                        m.parent = obj
                        # skin?
                        if do_skin and 'skin' in n:
                            try:
                                apply_skin(m, prim, int(n['skin']))
                            except Exception as e:
                                _log('Skin failed: %s' % e)
        for c in n.get('children', []):
            if 0 <= c < len(nodes):
                make_node_obj(c, obj)
        return obj

    # skin helper (basic: joints + weights)
    def apply_skin(mesh_obj, prim, skin_idx):
        if skin_idx < 0 or skin_idx >= len(skins):
            return
        sk = skins[skin_idx]
        joints = sk.get('joints', [])
        if not joints:
            return
        attrs = prim.get('attributes', {})
        if 'JOINTS_0' not in attrs or 'WEIGHTS_0' not in attrs:
            _log('Skin %d: mesh has no JOINTS_0/WEIGHTS_0, skipping' % skin_idx)
            return
        J = [int(v) for v in doc.accessor_data(attrs['JOINTS_0'])]
        W = [float(v) for v in doc.accessor_data(attrs['WEIGHTS_0'])]
        nj = len(J) // 4
        # ensure bone nodes exist
        bone_nodes = []
        for ji in joints:
            if ji in created_nodes:
                bone_nodes.append(created_nodes[ji])
            else:
                d = rt.Dummy()
                d.name = 'Joint_%d' % ji
                bone_nodes.append(d)
        sm = rt.Skin()
        rt.addModifier(mesh_obj, sm)
        try:
            rt.select(mesh_obj)
        except Exception:
            pass
        for b in bone_nodes:
            try:
                rt.skinOps.addBone(sm, b, 0)
            except Exception:
                try:
                    rt.skinOps.addBone(sm, b, 1)
                except Exception:
                    pass
        # set weights per vertex: skinOps.ReplaceVertexWeights boneID vertID weight
        # bone IDs in modifier are 1-based in add order
        try:
            nb = len(bone_nodes)
            for vi in range(nj):
                for k in range(4):
                    w = W[vi * 4 + k]
                    if w <= 0.0:
                        continue
                    j = J[vi * 4 + k]
                    try:
                        bidx = list(joints).index(j) + 1
                    except ValueError:
                        continue
                    try:
                        rt.skinOps.ReplaceVertexWeights(sm, vi + 1, bidx, w)
                    except Exception:
                        pass
        except Exception as e:
            _log('Skin weights failed: %s' % e)

    top_group = None
    if nodes and do_hier:
        if create_dummies:
            top_group = rt.Dummy()
            top_group.name = os.path.splitext(os.path.basename(path))[0][:50] or 'GLB_Root'
            for r in roots:
                make_node_obj(r, top_group)
        else:
            # No helpers: build meshes directly, bake node transform onto mesh object.
            # make_node_obj still creates dummies internally, so bypass it:
            for ni, n in enumerate(nodes):
                if 'mesh' not in n:
                    continue
                T, Q, S = node_local.get(ni, ((0, 0, 0), (0, 0, 0, 1), (1, 1, 1)))
                # accumulate parent chain transforms (simple: walk up via child->parent map)
                # build parent map once
                mdef = meshes[int(n['mesh'])] if 0 <= int(n['mesh']) < len(meshes) else None
                if mdef is None:
                    continue
                nm = n.get('name', 'Node_%d' % ni) or ('Node_%d' % ni)
                for pi, prim in enumerate(mdef.get('primitives', [])):
                    m = build_primitive(nm, prim, pi)
                    if m is None:
                        continue
                    try:
                        m.position = rt.Point3(T[0] * scale, T[1] * scale, T[2] * scale)
                        m.rotation = rt.quat(Q[0], Q[1], Q[2], Q[3])
                        m.scale = rt.Point3(S[0], S[1], S[2])
                    except Exception:
                        pass
                    # record pseudo-node for animation lookup (mesh takes node transform)
                    created_nodes[ni] = m
    elif nodes and not do_hier:
        # flat import: bake world transforms? simplified: import meshes at origin, ignore hierarchy
        for ni, n in enumerate(nodes):
            if 'mesh' in n:
                mdef = meshes[int(n['mesh'])]
                for pi, prim in enumerate(mdef.get('primitives', [])):
                    m = build_primitive(n.get('name', 'Node_%d' % ni), prim, pi)
                    if m is not None and top_group is not None:
                        m.parent = top_group
    else:
        # no nodes: direct meshes
        for mi, mdef in enumerate(meshes):
            for pi, prim in enumerate(mdef.get('primitives', [])):
                build_primitive('Mesh_%d' % mi, prim, pi)

    # ---- normalize (for unit-cube outputs like ComfyUI WhiteMesh) ----
    try:
        if target_size > 0 and len(created_meshes) > 0:
            bmin = [1e18, 1e18, 1e18]
            bmax = [-1e18, -1e18, -1e18]
            for m in created_meshes:
                try:
                    bb = m.max - m.min  # diagonal; use min/max corners
                    mn = m.min
                    mx = m.max
                    for i, (a, b) in enumerate(zip((mn.x, mn.y, mn.z), (mx.x, mx.y, mx.z))):
                        bmin[i] = min(bmin[i], a)
                        bmax[i] = max(bmax[i], b)
                except Exception:
                    pass
            cur = max(bmax[i] - bmin[i] for i in range(3))
            if cur > 1e-9:
                k = target_size / cur
                _log('Normalize: current size %s -> target %s (x%s)' % (cur, target_size, k))
                if top_group is not None:
                    top_group.scale = rt.Point3(
                        top_group.scale.x * k, top_group.scale.y * k, top_group.scale.z * k)
                else:
                    for m in created_meshes:
                        try:
                            m.scale = rt.Point3(m.scale.x * k, m.scale.y * k, m.scale.z * k)
                        except Exception:
                            pass
            else:
                _log('Normalize skipped: empty bbox')
    except Exception as e:
        _log('Normalize failed: %s' % e)

    # ---- animation (baked TRS) ----
    anim_count = 0
    if do_anim and do_hier and 'animations' in js:
        try:
            fps = 30.0
            try:
                fps = float(rt.frameRate)
            except Exception:
                pass
            for ai, anim in enumerate(js['animations']):
                chs = anim.get('channels', [])
                smps = anim.get('samplers', [])
                # group by node
                per_node = {}
                for ch in chs:
                    tgt = ch.get('target', {})
                    ni = tgt.get('node', -1)
                    pth = tgt.get('path', '')
                    si = ch.get('sampler', 0)
                    if si < 0 or si >= len(smps):
                        continue
                    smp = smps[si]
                    times = doc.accessor_data(smp['input'])
                    vals = doc.accessor_data(smp['output'])
                    interp = smp.get('interpolation', 'LINEAR')
                    per_node.setdefault(ni, []).append((pth, times, vals, interp))
                for ni, tracks in per_node.items():
                    if ni not in created_nodes:
                        continue
                    obj = created_nodes[ni]
                    # union times
                    tset = sorted(set(t for (_, t, _, _) in tracks for t in t))
                    if not tset:
                        continue
                    base_T, base_Q, base_S = node_local.get(ni, ((0, 0, 0), (0, 0, 0, 1), (1, 1, 1)))
                    # pre-sample each track at union times (nearest/linear on vec components)
                    def sample_track(times, vals, ncomp, t, interp):
                        if t <= times[0]:
                            return vals[:ncomp]
                        if t >= times[-1]:
                            return vals[(len(times) - 1) * ncomp:]
                        # find segment
                        for k in range(len(times) - 1):
                            if times[k] <= t <= times[k + 1]:
                                if interp == 'STEP':
                                    return vals[k * ncomp:(k + 1) * ncomp]
                                f = (t - times[k]) / max(1e-9, (times[k + 1] - times[k]))
                                a = vals[k * ncomp:(k + 1) * ncomp]
                                b = vals[(k + 1) * ncomp:(k + 2) * ncomp]
                                if ncomp == 4 and interp != 'STEP':
                                    # slerp-ish via nlerp for quats
                                    q = [ai + (bi - ai) * f for ai, bi in zip(a, b)]
                                    return list(q_normalize(q))
                                return [ai + (bi - ai) * f for ai, bi in zip(a, b)]
                        return vals[:ncomp]
                    with rt.animate(True):
                        for t in tset:
                            fr = t * fps
                            T, Q, S = base_T, base_Q, base_S
                            for (pth, times, vals, interp) in tracks:
                                if pth == 'translation':
                                    v = sample_track(times, vals, 3, t, interp)
                                    T = convert_pos(v, convert)
                                elif pth == 'rotation':
                                    v = sample_track(times, vals, 4, t, interp)
                                    Q = q_to_max_quat(v, convert)
                                elif pth == 'scale':
                                    v = sample_track(times, vals, 3, t, interp)
                                    S = convert_scale(v, convert)
                            try:
                                rt.at(rt.time(fr))(lambda: None)
                            except Exception:
                                pass
                            # set keys via slider + assignment inside animate context
                            try:
                                rt.sliderTime = rt.time(fr)
                                obj.position = rt.Point3(T[0] * scale, T[1] * scale, T[2] * scale)
                                obj.rotation = rt.quat(Q[0], Q[1], Q[2], Q[3])
                                obj.scale = rt.Point3(S[0], S[1], S[2])
                            except Exception:
                                pass
                    anim_count += 1
        except Exception as e:
            _log('Animation import failed: %s\n%s' % (e, traceback.format_exc()))

    rt.redrawViews()
    return {
        'meshes': len(created_meshes),
        'nodes': len(created_nodes),
        'materials': len(mat_cache),
        'animations': anim_count,
        'tmpdir': tmpdir,
    }


def GLB_IMPORT(path, scale=1.0, convert_up=True, import_materials=True,
               import_textures=True, import_hierarchy=True,
               import_animation=True, import_skin=True, flip_uv_v=True,
               auto_unit=True, target_size=0.0, create_dummies=False):
    opts = dict(scale=scale, convert_up=convert_up,
                import_materials=import_materials, import_textures=import_textures,
                import_hierarchy=import_hierarchy, import_animation=import_animation,
                import_skin=import_skin, flip_uv_v=flip_uv_v,
                auto_unit=auto_unit, target_size=target_size,
                create_dummies=create_dummies)
    try:
        res = import_glb_file(path, opts)
        _log('GLB import OK: %s' % res)
        return res
    except Exception as e:
        _log('GLB import FAILED: %s\n%s' % (e, traceback.format_exc()))
        raise
