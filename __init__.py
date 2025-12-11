bl_info = {
    "name": "BB Modeling toolkit",
    "category": "Mesh",
    "author": "Blender Bob",
    "version": (3, 0),
    "blender": (4, 5, 0),
    "location": "View3D > N panel > Modeling toolkit",
    "description": "Most used tools when modeling for gaming",
}

import bpy
import bmesh
from mathutils import Vector
from math import radians

# --------------------------------------------------------------------
# Helper: Concave faces
# --------------------------------------------------------------------
def is_concave(f):
    # A face is concave if the polygon formed by its vertices is not convex
    verts = [v.co for v in f.verts]
    if len(verts) < 4:
        return False  # Triangles and quads are convex by definition

    # Compute center
    center = sum(verts, Vector((0, 0, 0))) / len(verts)

    # Get normal
    normal = f.normal

    # Find basis vectors u, v perpendicular to normal
    arb = Vector((1, 0, 0)) if abs(normal.x) < 0.5 else Vector((0, 1, 0))
    u = normal.cross(arb).normalized()
    v = normal.cross(u).normalized()

    # Project vertices to 2D plane
    points_2d = [((vert - center).dot(u), (vert - center).dot(v)) for vert in verts]

    # 2D cross product helper
    def cross2d(p1, p2, p3):
        a_x = p2[0] - p1[0]
        a_y = p2[1] - p1[1]
        b_x = p3[0] - p2[0]
        b_y = p3[1] - p2[1]
        return a_x * b_y - a_y * b_x

    # Compute signs of turns
    signs = []
    n = len(points_2d)
    for i in range(n):
        c = cross2d(points_2d[i], points_2d[(i + 1) % n], points_2d[(i + 2) % n])
        signs.append(c)

    # If signs are not all positive or all negative, face is concave
    all_pos = all(s >= 0 for s in signs)
    all_neg = all(s <= 0 for s in signs)
    return not (all_pos or all_neg)


# --------------------------------------------------------------------
# Helper: Ensure Edit Mode
# --------------------------------------------------------------------
def ensure_edit_mode(obj, select_mode=(True, False, False)):
    """Ensure object is in EDIT mode and selection type is set.
       select_mode is a tuple: (vertex, edge, face)"""
    if obj.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = select_mode


# --------------------------------------------------------------------
# Helper: Merge overlapping vertices (currently unused, but kept)
# --------------------------------------------------------------------
def merge_overlapping_vertices(obj, threshold=0.0001):
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    bpy.ops.mesh.select_all(action='DESELECT')

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    # Select overlapping verts
    for i, v1 in enumerate(bm.verts):
        for j in range(i + 1, len(bm.verts)):
            v2 = bm.verts[j]
            if (v1.co - v2.co).length <= threshold:
                v1.select = True
                v2.select = True

    bmesh.update_edit_mesh(obj.data)

    # Merge selected vertices by distance
    bpy.ops.mesh.remove_doubles(threshold=threshold)


# --------------------------------------------------------------------
# Helper: Select overlapping vertices
# --------------------------------------------------------------------
def select_overlapping_vertices(obj, threshold=0.0001):
    ensure_edit_mode(obj, select_mode=(True, False, False))  # Vertex select

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    # Deselect all
    for v in bm.verts:
        v.select = False

    # Compare vertices positions
    seen = {}
    for v in bm.verts:
        key = (round(v.co.x / threshold),
               round(v.co.y / threshold),
               round(v.co.z / threshold))
        if key in seen:
            v.select = True
            seen[key].select = True
        else:
            seen[key] = v

    bmesh.update_edit_mesh(obj.data)

# --------------------------------------------------------------------
# Helper: Toggle isolate overlapping vertices
# --------------------------------------------------------------------
def toggle_isolate_overlapping_vertices(context, threshold=0.0001):
    objs = [obj for obj in context.selected_objects if obj.type == 'MESH']
    if not objs:
        return {'CANCELLED'}

    if context.view_layer.objects.active not in objs:
        context.view_layer.objects.active = objs[0]

    if context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    bmeshes = [bmesh.from_edit_mesh(obj.data) for obj in objs]

    current = getattr(context.scene, "active_isolate", "")
    any_hidden = any(f.hide for bm in bmeshes for f in bm.faces)

    # If same isolate clicked → revert
    if current == "OVERLAP_VERTS":
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

        context.space_data.shading.type = context.scene.original_shading
        context.tool_settings.mesh_select_mode = context.scene.original_select_mode
        context.scene.active_isolate = ""

        for obj in objs:
            bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}

    # Different isolate or something hidden → clean state
    if current or any_hidden:
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

    # Store original shading & selection mode
    context.scene.original_shading = context.space_data.shading.type
    context.scene.original_select_mode = context.tool_settings.mesh_select_mode[:]

    # Vertex select mode
    context.tool_settings.mesh_select_mode = (True, False, False)

    # Deselect all vertices defensively
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            v.select = False
        bmesh.update_edit_mesh(obj.data)

    # Use helper to select overlapping verts on each object
    for obj in objs:
        select_overlapping_vertices(obj, threshold)

    # Hide unselected geometry if not showing wireframe
    if not context.scene.show_wire_isolate:
        bpy.ops.mesh.hide(unselected=True)

    # Set shading
    context.space_data.shading.type = (
        'WIREFRAME' if context.scene.show_wire_isolate else 'SOLID'
    )

    context.scene.active_isolate = "OVERLAP_VERTS"
    return {'FINISHED'}


# --------------------------------------------------------------------
# Helper: Toggle isolate overlapping faces
# --------------------------------------------------------------------
def toggle_isolate_overlapping_faces(context, threshold=0.0001):
    objs = [obj for obj in context.selected_objects if obj.type == 'MESH']
    if not objs:
        return {'CANCELLED'}

    if context.view_layer.objects.active not in objs:
        context.view_layer.objects.active = objs[0]

    if context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    bmeshes = [bmesh.from_edit_mesh(obj.data) for obj in objs]

    current = getattr(context.scene, "active_isolate", "")
    any_hidden = any(f.hide for bm in bmeshes for f in bm.faces)

    # If same isolate clicked → revert
    if current == "OVERLAP_FACES":
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

        context.space_data.shading.type = context.scene.original_shading
        context.tool_settings.mesh_select_mode = context.scene.original_select_mode
        context.scene.active_isolate = ""

        for obj in objs:
            bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}

    # Different isolate or something hidden → clean state
    if current or any_hidden:
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

    # Store original shading & selection mode
    context.scene.original_shading = context.space_data.shading.type
    context.scene.original_select_mode = context.tool_settings.mesh_select_mode[:]

    # Face select mode
    context.tool_settings.mesh_select_mode = (False, False, True)

    # Deselect all faces defensively
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        for f in bm.faces:
            f.select = False
        bmesh.update_edit_mesh(obj.data)

    # Use helper to select overlapping faces on each object
    for obj in objs:
        select_overlapping_faces_fast(obj, threshold)

    # Hide unselected geometry if not showing wireframe
    if not context.scene.show_wire_isolate:
        bpy.ops.mesh.hide(unselected=True)

    # Set shading
    context.space_data.shading.type = (
        'WIREFRAME' if context.scene.show_wire_isolate else 'SOLID'
    )

    context.scene.active_isolate = "OVERLAP_FACES"
    return {'FINISHED'}

# --------------------------------------------------------------------
# Helper: Delete overlapping faces (keep one)
# --------------------------------------------------------------------
def fix_overlapping_faces_fast(obj, threshold=0.0001):
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    me = obj.data
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table()

    face_dict = {}
    factor = 1 / threshold  # scale factor for rounding

    faces_to_delete = []

    for f in bm.faces:
        key = tuple(sorted(
            (round(v.co.x * factor),
             round(v.co.y * factor),
             round(v.co.z * factor)) for v in f.verts
        ))

        if key in face_dict:
            faces_to_delete.append(f)
        else:
            face_dict[key] = f

    if faces_to_delete:
        bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES')

    bmesh.update_edit_mesh(me)


# --------------------------------------------------------------------
# Helper: Select overlapping faces (fast)
# --------------------------------------------------------------------
def select_overlapping_faces_fast(obj, threshold=0.0001):
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    me = obj.data
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table()

    # Deselect all faces first
    for f in bm.faces:
        f.select = False

    face_dict = {}
    factor = 1 / threshold

    for f in bm.faces:
        key = tuple(sorted(
            (round(v.co.x * factor),
             round(v.co.y * factor),
             round(v.co.z * factor)) for v in f.verts
        ))
        if key in face_dict:
            f.select = True
            face_dict[key].select = True
        else:
            face_dict[key] = f

    bmesh.update_edit_mesh(me)


# --------------------------------------------------------------------
# Helper: Select non-manifold (still used conceptually, not exposed)
# --------------------------------------------------------------------
def select_non_manifold_full(obj):
    if obj is None or obj.type != 'MESH':
        return

    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    me = obj.data
    bm = bmesh.from_edit_mesh(me)

    # Deselect all first
    for v in bm.verts:
        v.select = False
    for e in bm.edges:
        e.select = False
    for f in bm.faces:
        f.select = False

    # Detect non-manifold edges
    non_manifold_edges = [e for e in bm.edges if len(e.link_faces) != 2]
    for e in non_manifold_edges:
        e.select = True
        for v in e.verts:
            v.select = True

    # Detect loose vertices (no faces)
    loose_verts = [v for v in bm.verts if len(v.link_faces) == 0]
    for v in loose_verts:
        v.select = True

    bmesh.update_edit_mesh(me)

    bpy.context.tool_settings.mesh_select_mode = (True, False, False)


# --------------------------------------------------------------------
# Helper: decimate slider
# --------------------------------------------------------------------
def update_decimate_angle(self, context):
    angle = radians(context.scene.decimate_angle_limit)

    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue

        dec = obj.modifiers.get("DecimatePlanar")
        if dec:
            dec.angle_limit = angle


# --------------------------------------------------------------------
# Helper: Toggle isolate faces (multi-object)
# --------------------------------------------------------------------
def toggle_isolate_faces(context, face_type):
    objs = [obj for obj in context.selected_objects if obj.type == 'MESH']
    if not objs:
        return {'CANCELLED'}

    if context.view_layer.objects.active not in objs:
        context.view_layer.objects.active = objs[0]

    if context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    bmeshes = [bmesh.from_edit_mesh(obj.data) for obj in objs]

    current = getattr(context.scene, "active_isolate", "")
    any_hidden = any(f.hide for bm in bmeshes for f in bm.faces)

    # If same isolate clicked → revert
    if current == face_type:
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

        context.space_data.shading.type = context.scene.original_shading
        context.tool_settings.mesh_select_mode = context.scene.original_select_mode
        context.scene.active_isolate = ""

        for obj, bm in zip(objs, bmeshes):
            bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}

    # Different isolate or something hidden → clean state
    if current or any_hidden:
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

    context.scene.original_shading = context.space_data.shading.type
    context.scene.original_select_mode = context.tool_settings.mesh_select_mode[:]

    context.tool_settings.mesh_select_mode = (False, False, True)

    for bm in bmeshes:
        for f in bm.faces:
            f.select = False

    # Select faces according to type
    for bm in bmeshes:
        if face_type == "NGONS":
            for f in bm.faces:
                f.select = len(f.verts) > 4
        elif face_type == "TRIS":
            for f in bm.faces:
                f.select = len(f.verts) == 3
        elif face_type == "NON_MANIFOLD":
            for f in bm.faces:
                f.select = any(not e.is_manifold for e in f.edges)
        elif face_type == "CONCAVE":
            for f in bm.faces:
                f.select = is_concave(f)

    for obj, bm in zip(objs, bmeshes):
        bmesh.update_edit_mesh(obj.data)

    if not context.scene.show_wire_isolate:
        bpy.ops.mesh.hide(unselected=True)

    context.space_data.shading.type = (
        'WIREFRAME' if context.scene.show_wire_isolate else 'SOLID'
    )

    context.scene.active_isolate = face_type
    return {'FINISHED'}


# ====================================================================
# OPERATORS (ordered by UI sections)
# ====================================================================
# --------------------------------------------------------------------
# ISOLATE SECTION
# --------------------------------------------------------------------
class MESH_OT_isolate_triangles(bpy.types.Operator):
    bl_idname = "mesh.isolate_triangles"
    bl_label = "Isolate Triangles"
    bl_description = "Isolate only triangular faces on the selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return toggle_isolate_faces(context, "TRIS")


class MESH_OT_isolate_ngons(bpy.types.Operator):
    bl_idname = "mesh.isolate_ngons"
    bl_label = "Isolate nGons"
    bl_description = "Isolate faces with more than 4 sides on the selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return toggle_isolate_faces(context, "NGONS")


class MESH_OT_isolate_non_manifold(bpy.types.Operator):
    bl_idname = "mesh.isolate_non_manifold"
    bl_label = "Isolate Non-Manifold"
    bl_description = "Isolate non-manifold regions on the selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return toggle_isolate_faces(context, "NON_MANIFOLD")


class MESH_OT_isolate_concave(bpy.types.Operator):
    bl_idname = "mesh.isolate_concave"
    bl_label = "Isolate Concave"
    bl_description = "Isolate concave faces on the selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return toggle_isolate_faces(context, "CONCAVE")


class MESH_OT_select_overlapping_vertices(bpy.types.Operator):
    bl_idname = "mesh.select_overlapping_vertices"
    bl_label = "Select Overlapping Verts"
    bl_description = "Isolate and select vertices that share the same position within a distance threshold"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Distance Threshold",
        default=0.0001,
        description="Distance to consider vertices overlapping"
    )

    def execute(self, context):
        return toggle_isolate_overlapping_vertices(context, self.threshold)


class MESH_OT_select_overlapping_faces(bpy.types.Operator):
    bl_idname = "mesh.select_overlapping_faces"
    bl_label = "Select Overlapping Faces"
    bl_description = "Isolate and select faces that overlap (duplicates) on selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Distance Threshold",
        default=0.0001,
        description="Maximum distance to consider faces overlapping"
    )

    def execute(self, context):
        return toggle_isolate_overlapping_faces(context, self.threshold)


# --------------------------------------------------------------------
# GEOMETRY SECTION
# --------------------------------------------------------------------
class MESH_OT_triangulate(bpy.types.Operator):
    bl_idname = "mesh.fix_triangulate"
    bl_label = "Triangulate"
    bl_description = "Convert quads to triangles on the active mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}

        if context.mode == 'EDIT_MESH':
            bpy.ops.mesh.quads_convert_to_tris()
        else:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.quads_convert_to_tris()
            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}


class MESH_OT_tris_to_quads(bpy.types.Operator):
    bl_idname = "mesh.fix_tris_to_quads"
    bl_label = "Tris to Quads"
    bl_description = "Convert triangles back to quads where possible on the active mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}

        if context.mode == 'EDIT_MESH':
            bpy.ops.mesh.tris_convert_to_quads()
        else:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.tris_convert_to_quads()
            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}


class OBJECT_OT_apply_all_modifiers(bpy.types.Operator):
    bl_idname = "object.apply_all_modifiers"
    bl_label = "Apply All Modifiers"
    bl_description = "Apply every modifier, in order, on each selected mesh object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj in bpy.context.selected_objects:
            if obj.type != 'MESH':
                continue

            for mod in list(obj.modifiers):
                try:
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except Exception as e:
                    self.report(
                        {'WARNING'},
                        f"Could not apply {mod.name} on {obj.name}: {e}"
                    )

        return {'FINISHED'}


class OBJECT_OT_delete_all_modifiers(bpy.types.Operator):
    bl_idname = "object.delete_all_modifiers"
    bl_label = "Delete All Modifiers"
    bl_description = "Remove all modifiers from each selected mesh object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in bpy.context.selected_objects:
            if obj.type != 'MESH':
                continue

            for mod in list(obj.modifiers):
                try:
                    obj.modifiers.remove(mod)
                except Exception as e:
                    self.report(
                        {'WARNING'},
                        f"Could not remove {mod.name} on {obj.name}: {e}"
                    )

        return {'FINISHED'}


class MESH_OT_edge_rotate(bpy.types.Operator):
    bl_idname = "mesh.edge_rotate_custom"
    bl_label = "Rotate Edge"
    bl_description = "Rotate selected edge(s) to an alternate diagonal"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.edge_rotate(use_ccw=True)
        return {'FINISHED'}


# --------------------------------------------------------------------
# FIX SECTION
# --------------------------------------------------------------------
class MESH_OT_fix_ngone(bpy.types.Operator):
    bl_idname = "mesh.fix_ngone"
    bl_label = "Fix nGons"
    bl_description = "Triangulate n-gons then convert back to quads where possible"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']

        for obj in selected:
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')

            bm = bmesh.from_edit_mesh(obj.data)
            bm.faces.ensure_lookup_table()

            for f in bm.faces:
                f.select = len(f.verts) > 4

            bmesh.update_edit_mesh(obj.data)

            bpy.ops.mesh.quads_convert_to_tris()
            bpy.ops.mesh.tris_convert_to_quads()

            bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}


class MESH_OT_cleanup(bpy.types.Operator):
    bl_idname = "mesh.cleanup_mesh"
    bl_label = "Cleanup"
    bl_description = "Merge overlapping verts, remove duplicate faces and loose elements, then recalc normals"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Distance Threshold",
        default=0.0001,
        description="Threshold for merging overlapping vertices"
    )

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']

        for obj in selected:
            context.view_layer.objects.active = obj

            bpy.ops.object.mode_set(mode='EDIT')
            me = obj.data
            bm = bmesh.from_edit_mesh(me)

            # 1. Merge overlapping vertices
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=self.threshold)

            # 2. Remove overlapping faces
            fix_overlapping_faces_fast(obj, self.threshold)

            # 3. Remove loose verts
            loose_verts = [
                v for v in bm.verts
                if len(v.link_edges) == 0 and len(v.link_faces) == 0
            ]
            if loose_verts:
                bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')

            # 4. Remove loose edges
            loose_edges = [e for e in bm.edges if len(e.link_faces) == 0]
            if loose_edges:
                bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')

            bmesh.update_edit_mesh(me)

            # 5. Recalculate normals
            prev_mode = context.tool_settings.mesh_select_mode[:]

            context.tool_settings.mesh_select_mode = (False, False, True)
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.normals_make_consistent(inside=False)

            context.tool_settings.mesh_select_mode = prev_mode
            bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}


# --------------------------------------------------------------------
# DECIMATE SECTION
# --------------------------------------------------------------------
class MESH_OT_add_decimate(bpy.types.Operator):
    bl_idname = "mesh.add_planar_decimate"
    bl_label = "Decimate"
    bl_description = "Add planar (dissolve) decimate modifier to selected meshes using the Angle Limit"
    bl_options = {'REGISTER', 'UNDO'}

    angle_limit: bpy.props.FloatProperty(
        name="Angle",
        default=1.0,
        min=0.0,
        max=30.0,
        description="Planar Decimate angle limit"
    )

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        angle = radians(self.angle_limit)

        for obj in context.selected_objects:
            if obj.type != "MESH":
                continue

            for m in list(obj.modifiers):
                if m.type == 'DECIMATE' and m.name == "DecimatePlanar":
                    obj.modifiers.remove(m)

            dec = obj.modifiers.new(name="DecimatePlanar", type='DECIMATE')
            dec.decimate_type = 'DISSOLVE'
            dec.angle_limit = angle
            dec.delimit = {'NORMAL'}

        context.scene.decimate_angle_limit = self.angle_limit

        self.report({'INFO'}, "Decimate added to selected objects")
        return {'FINISHED'}


class MESH_OT_apply_decimate(bpy.types.Operator):
    bl_idname = "mesh.apply_planar_decimate"
    bl_label = "Apply Decimate"
    bl_description = "Apply the DecimatePlanar modifier on all selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj in context.selected_objects:
            if obj.type != "MESH":
                continue

            dec = obj.modifiers.get("DecimatePlanar")

            if dec:
                context.view_layer.objects.active = obj
                try:
                    bpy.ops.object.modifier_apply(modifier=dec.name)
                except Exception:
                    self.report({'WARNING'}, f"Could not apply decimate on {obj.name}")

        return {'FINISHED'}


# --------------------------------------------------------------------
# PANEL
# --------------------------------------------------------------------
class VIEW3D_PT_gaming_toolkit(bpy.types.Panel):
    bl_label = "BB Modeling Toolkit"
    bl_category = "Tool"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout

        # Isolate Section (now includes Overlapping tools)
        box = layout.box()
        box.label(text="Isolate", icon='RESTRICT_SELECT_OFF')
        box.prop(context.scene, "show_wire_isolate", text="Show Wireframe")
        box.operator("mesh.isolate_triangles", text="Tris")
        box.operator("mesh.isolate_ngons", text="nGons")
        box.operator("mesh.isolate_non_manifold", text="Non-Manifold")
        box.operator("mesh.isolate_concave", text="Concave")
        box.operator("mesh.select_overlapping_vertices", text="Overlapping Verts")
        box.operator("mesh.select_overlapping_faces", text="Overlapping Faces")

        # Geometry Section
        box = layout.box()
        box.label(text="Geometry", icon='MODIFIER')
        box.operator("mesh.fix_triangulate", text="Triangulate")
        box.operator("mesh.fix_tris_to_quads", text="Tris → Quads")
        box.operator("object.apply_all_modifiers", icon='CHECKMARK')
        box.operator("object.delete_all_modifiers", icon='TRASH')
        if context.mode == 'EDIT_MESH':
            box.operator("mesh.edge_rotate_custom", text="Rotate Edge")

        # Fix Section
        box = layout.box()
        box.label(text="Fix", icon='MODIFIER')
        box.operator("mesh.fix_ngone", text="nGons")
        box.operator("mesh.cleanup_mesh", text="Cleanup")

        # Decimate Section
        box = layout.box()
        box.label(text="Decimate", icon='MODIFIER')
        box.prop(context.scene, "decimate_angle_limit", text="Angle Limit")
        row = box.row()
        row.operator("mesh.add_planar_decimate", text="Decimate (Planar)")
        box.operator("mesh.apply_planar_decimate", text="Apply Decimate")


# --------------------------------------------------------------------
# REGISTER
# --------------------------------------------------------------------
classes = (
    # Isolate + Overlapping
    MESH_OT_isolate_triangles,
    MESH_OT_isolate_ngons,
    MESH_OT_isolate_non_manifold,
    MESH_OT_isolate_concave,
    MESH_OT_select_overlapping_vertices,
    MESH_OT_select_overlapping_faces,

    # Geometry
    MESH_OT_triangulate,
    MESH_OT_tris_to_quads,
    OBJECT_OT_apply_all_modifiers,
    OBJECT_OT_delete_all_modifiers,
    MESH_OT_edge_rotate,

    # Fix
    MESH_OT_fix_ngone,
    MESH_OT_cleanup,

    # Decimate
    MESH_OT_add_decimate,
    MESH_OT_apply_decimate,

    # Panel
    VIEW3D_PT_gaming_toolkit,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Scene.show_wire_isolate = bpy.props.BoolProperty(
        name="Show Wireframe",
        default=True
    )
    bpy.types.Scene.active_isolate = bpy.props.StringProperty(
        name="Active Isolate",
        default=""
    )
    bpy.types.Scene.original_shading = bpy.props.StringProperty(
        name="Original Shading",
        default="SOLID"
    )
    bpy.types.Scene.original_select_mode = bpy.props.BoolVectorProperty(
        name="Original Select Mode",
        size=3,
        default=(False, False, True)
    )

    bpy.types.Scene.decimate_angle_limit = bpy.props.FloatProperty(
        name="Angle",
        default=1.0,
        min=0.0,
        max=30.0,
        description="Planar Decimate angle limit",
        update=update_decimate_angle
    )


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

    del bpy.types.Scene.show_wire_isolate
    del bpy.types.Scene.active_isolate
    del bpy.types.Scene.original_shading
    del bpy.types.Scene.original_select_mode
    del bpy.types.Scene.decimate_angle_limit


if __name__ == "__main__":
    register()
