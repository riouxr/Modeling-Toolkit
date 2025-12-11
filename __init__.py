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
    center = sum(verts, Vector((0,0,0))) / len(verts)
    
    # Get normal
    normal = f.normal
    
    # Find basis vectors u, v perpendicular to normal
    arb = Vector((1,0,0)) if abs(normal.x) < 0.5 else Vector((0,1,0))
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
        c = cross2d(points_2d[i], points_2d[(i+1)%n], points_2d[(i+2)%n])
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
# Helper: Select triangles
# --------------------------------------------------------------------
def select_tris(obj):
    ensure_edit_mode(obj, select_mode=(False, False, True))  # Face select
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select = len(f.verts) == 3
    bmesh.update_edit_mesh(obj.data)

# --------------------------------------------------------------------
# Helper: Merge overlapping vertices
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
        key = (round(v.co.x / threshold), round(v.co.y / threshold), round(v.co.z / threshold))
        if key in seen:
            v.select = True
            seen[key].select = True
        else:
            seen[key] = v

    bmesh.update_edit_mesh(obj.data)

# --------------------------------------------------------------------
# Helper: Find overlapping faces
# --------------------------------------------------------------------
def select_overlapping_faces_fast(obj, threshold=0.0001):
    ensure_edit_mode(obj, select_mode=(False, False, True))  # Face select

    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    for f in bm.faces:
        f.select = False

    factor = 1 / threshold
    face_dict = {}

    for f in bm.faces:
        key = tuple(sorted((round(v.co.x * factor), round(v.co.y * factor), round(v.co.z * factor)) for v in f.verts))
        if key in face_dict:
            f.select = True
            face_dict[key].select = True  # select the first face too
        else:
            face_dict[key] = f

    bmesh.update_edit_mesh(obj.data)


# --------------------------------------------------------------------
# Helper: Select non-manifold
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
    
    # Switch to vertex select mode so selected verts are visible
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)



# --------------------------------------------------------------------
# Helper: Delete overlapping faces (keep one)
# --------------------------------------------------------------------
def fix_overlapping_faces_fast(obj, threshold=0.0001):
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    me = obj.data
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table()

    # Dictionary to track unique faces by their rounded vertex coordinates
    face_dict = {}
    factor = 1 / threshold  # scale factor for rounding

    faces_to_delete = []

    for f in bm.faces:
        # Create a key based on rounded vertex positions
        key = tuple(sorted(
            (round(v.co.x * factor), round(v.co.y * factor), round(v.co.z * factor)) for v in f.verts
        ))

        if key in face_dict:
            # Duplicate face found → mark for deletion
            faces_to_delete.append(f)
        else:
            # First occurrence → store in dictionary
            face_dict[key] = f

    # Delete all duplicates in one operation
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

    # Dictionary to track faces by their rounded vertex coordinates
    face_dict = {}         # <-- initialize this BEFORE using it
    factor = 1 / threshold # scale factor for rounding

    for f in bm.faces:
        # Create a hashable key: tuple of sorted rounded vertex coords
        key = tuple(sorted((round(v.co.x * factor), round(v.co.y * factor), round(v.co.z * factor)) for v in f.verts))
        if key in face_dict:
            f.select = True                # select current face
            face_dict[key].select = True   # select the first face too
        else:
            face_dict[key] = f

    bmesh.update_edit_mesh(me)

# --------------------------------------------------------------------
# Helper: decimate slider
# --------------------------------------------------------------------
def update_decimate_angle(self, context):
    obj = context.object
    if not obj or obj.type != 'MESH':
        return
    dec = obj.modifiers.get("DecimatePlanar")
    if dec:
        from math import radians
        dec.angle_limit = radians(context.scene.decimate_angle_limit)

# --------------------------------------------------------------------
# Helper: detect n-gons and select faces
# --------------------------------------------------------------------
def select_ngons(obj):
    ensure_edit_mode(obj, select_mode=(False, False, True))  # Face select
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select = len(f.verts) > 4
    bmesh.update_edit_mesh(obj.data)


# --------------------------------------------------------------------
# Operator: Select Overlapping Faces
# --------------------------------------------------------------------
class MESH_OT_select_overlapping_faces(bpy.types.Operator):
    bl_idname = "mesh.select_overlapping_faces"
    bl_label = "Select Overlapping Faces"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Distance Threshold",
        default=0.0001,
        description="Maximum distance to consider faces overlapping"
    )

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        select_overlapping_faces_fast(obj, self.threshold)
        return {'FINISHED'}


# --------------------------------------------------------------------
# Operator: Select Overlapping Vertices
# --------------------------------------------------------------------
class MESH_OT_select_overlapping_vertices(bpy.types.Operator):
    bl_idname = "mesh.select_overlapping_vertices"
    bl_label = "Select Overlapping Verts"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Distance Threshold",
        default=0.0001,
        description="Distance to consider vertices overlapping"
    )

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}
        select_overlapping_vertices(obj, self.threshold)
        return {'FINISHED'}


# --------------------------------------------------------------------
# Operator: Select Triangles
# --------------------------------------------------------------------
class MESH_OT_select_tris(bpy.types.Operator):
    bl_idname = "mesh.select_tris"
    bl_label = "Select Tris"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}
        select_tris(obj)
        return {'FINISHED'}    

# --------------------------------------------------------------------
# Operator: Select n-gons
# --------------------------------------------------------------------
class MESH_OT_select_ngons(bpy.types.Operator):
    bl_idname = "mesh.select_ngons"
    bl_label = "Select nGons"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}
        select_ngons(obj)
        return {'FINISHED'}

# --------------------------------------------------------------------
# Operator: Revert View (unhide all)
# --------------------------------------------------------------------
class MESH_OT_revert_view(bpy.types.Operator):
    bl_idname = "mesh.revert_view"
    bl_label = "Revert View"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}

        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

        return {'FINISHED'}

# --------------------------------------------------------------------
# Operator: Fix nGones
# --------------------------------------------------------------------
class MESH_OT_fix_ngone(bpy.types.Operator):
    bl_idname = "mesh.fix_ngone"
    bl_label = "Fix nGons"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        # Select only n-gons
        select_ngons(obj)

        # Convert selected n-gons to tris and back to quads
        bpy.ops.mesh.quads_convert_to_tris()
        bpy.ops.mesh.tris_convert_to_quads()
        return {'FINISHED'}

# --------------------------------------------------------------------
# Operator: Triangulate
# --------------------------------------------------------------------
class MESH_OT_triangulate(bpy.types.Operator):
    bl_idname = "mesh.fix_triangulate"
    bl_label = "Triangulate"
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

# --------------------------------------------------------------------
# Operator: Tris → Quads
# --------------------------------------------------------------------
class MESH_OT_tris_to_quads(bpy.types.Operator):
    bl_idname = "mesh.fix_tris_to_quads"
    bl_label = "Tris to Quads"
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

# --------------------------------------------------------------------
# Operator: Rotate edges (single button)
# --------------------------------------------------------------------
class MESH_OT_edge_rotate(bpy.types.Operator):
    bl_idname = "mesh.edge_rotate_custom"
    bl_label = "Rotate Edge"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.edge_rotate(use_ccw=True)
        return {'FINISHED'}

# --------------------------------------------------------------------
# Helper: Toggle isolate faces (add concave)
# --------------------------------------------------------------------
def toggle_isolate_faces(context, face_type):
    obj = context.object
    if obj is None or obj.type != 'MESH':
        return {'CANCELLED'}

    if context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')

    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    current = context.scene.active_isolate if hasattr(context.scene, "active_isolate") else None
    any_hidden = any(f.hide for f in bm.faces)

    if current == face_type:
        # Same isolate clicked → revert
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')
        context.space_data.shading.type = context.scene.original_shading
        context.tool_settings.mesh_select_mode = context.scene.original_select_mode
        context.scene.active_isolate = ""
        return {'FINISHED'}

    if current or any_hidden:
        # Different isolate clicked or hidden → revert first
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='DESELECT')

    # Store originals if starting new isolate
    context.scene.original_shading = context.space_data.shading.type
    context.scene.original_select_mode = context.tool_settings.mesh_select_mode[:]

    # Set to face select mode
    context.tool_settings.mesh_select_mode = (False, False, True)

    # Select new faces
    for f in bm.faces:
        f.select = False

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

    bmesh.update_edit_mesh(obj.data)

    # Hide unselected only if not showing wireframe
    if not context.scene.show_wire_isolate:
        bpy.ops.mesh.hide(unselected=True)

    # Set shading
    if context.scene.show_wire_isolate:
        context.space_data.shading.type = 'WIREFRAME'
    else:
        context.space_data.shading.type = 'SOLID'

    context.scene.active_isolate = face_type
    return {'FINISHED'}

# --------------------------------------------------------------------
# Operator: Decimate (Planar)
# --------------------------------------------------------------------
class MESH_OT_add_decimate(bpy.types.Operator):
    bl_idname = "mesh.add_planar_decimate"
    bl_label = "Decimate"
    bl_options = {'REGISTER', 'UNDO'}

    angle_limit: bpy.props.FloatProperty(
        name="Angle",
        default=1.0,
        min=0.0,
        max=30.0,
        description="Planar Decimate angle limit"
    )

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != "MESH":
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Remove existing DecimatePlanar modifier
        for m in list(obj.modifiers):
            if m.type == 'DECIMATE' and m.name == "DecimatePlanar":
                obj.modifiers.remove(m)

        # Add new Decimate modifier
        dec = obj.modifiers.new(name="DecimatePlanar", type='DECIMATE')
        dec.decimate_type = 'DISSOLVE'
        dec.angle_limit = radians(self.angle_limit)
        dec.delimit = {'NORMAL'}

        # Make slider match new modifier
        context.scene.decimate_angle_limit = self.angle_limit

        self.report({'INFO'}, "DecimatePlanar added")
        return {'FINISHED'}

# --------------------------------------------------------------------
# Operator: Cleanup
# --------------------------------------------------------------------
class MESH_OT_cleanup(bpy.types.Operator):
    bl_idname = "mesh.cleanup_mesh"
    bl_label = "Cleanup"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Distance Threshold",
        default=0.0001,
        description="Threshold for merging overlapping vertices"
    )

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        # Ensure edit mode
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        # ----------------------------
        # 1. Merge overlapping vertices
        # ----------------------------
        bmesh.ops.remove_doubles(
            bm,
            verts=bm.verts,
            dist=self.threshold
        )

        # ----------------------------
        # 2. Remove overlapping faces
        # ----------------------------
        fix_overlapping_faces_fast(obj, self.threshold)

        # ----------------------------
        # 3. Delete loose vertices
        # ----------------------------
        loose_verts = [v for v in bm.verts if len(v.link_edges) == 0 and len(v.link_faces) == 0]
        if loose_verts:
            bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')

        # ----------------------------
        # 4. Delete loose edges (no faces attached)
        # ----------------------------
        loose_edges = [e for e in bm.edges if len(e.link_faces) == 0]
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')

        bmesh.update_edit_mesh(me)

        # ----------------------------
        # 5. Recalculate normals (outside)
        # ----------------------------
        bpy.ops.mesh.normals_make_consistent(inside=False)

        self.report({'INFO'}, "Cleanup complete (Merged, removed duplicates, removed loose geo, normals fixed)")
        return {'FINISHED'}


# --------------------------------------------------------------------
# Operator: Apply Decimate
# --------------------------------------------------------------------
class MESH_OT_apply_decimate(bpy.types.Operator):
    bl_idname = "mesh.apply_planar_decimate"
    bl_label = "Apply Decimate"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != "MESH":
            return {'CANCELLED'}

        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        dec = obj.modifiers.get("DecimatePlanar")
        if dec:
            bpy.ops.object.modifier_apply(modifier=dec.name)
        else:
            self.report({'WARNING'}, "No DecimatePlanar modifier found")

        return {'FINISHED'}


# --------------------------------------------------------------------
# Operator: Isolate Non-Manifold (toggle)
# --------------------------------------------------------------------
class MESH_OT_isolate_non_manifold(bpy.types.Operator):
    bl_idname = "mesh.isolate_non_manifold"
    bl_label = "Isolate Non-Manifold"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        current = getattr(context.scene, "active_isolate", None)
        any_hidden = any(f.hide for f in bm.faces)

        # Revert if same isolate
        if current == "NON_MANIFOLD":
            bpy.ops.mesh.reveal()
            bpy.ops.mesh.select_all(action='DESELECT')
            context.space_data.shading.type = context.scene.original_shading
            context.tool_settings.mesh_select_mode = context.scene.original_select_mode[:]
            context.scene.active_isolate = ""
            return {'FINISHED'}

        # Revert first if needed
        if current or any_hidden:
            bpy.ops.mesh.reveal()
            bpy.ops.mesh.select_all(action='DESELECT')

        # Store original settings
        context.scene.original_shading = context.space_data.shading.type
        context.scene.original_select_mode = context.tool_settings.mesh_select_mode[:]

        # Select non-manifold vertices
        select_non_manifold_full(obj)

        # Hide unselected faces if not showing wireframe
        if not context.scene.show_wire_isolate:
            bpy.ops.mesh.hide(unselected=True)

        # Adjust shading
        context.space_data.shading.type = 'WIREFRAME' if context.scene.show_wire_isolate else 'SOLID'

        context.scene.active_isolate = "NON_MANIFOLD"
        return {'FINISHED'}


# --------------------------------------------------------------------
# Operator: Isolate n-gons (toggle)
# --------------------------------------------------------------------
class MESH_OT_isolate_ngons(bpy.types.Operator):
    bl_idname = "mesh.isolate_ngons"
    bl_label = "Isolate nGons"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return toggle_isolate_faces(context, "NGONS")

# --------------------------------------------------------------------
# Operator: Isolate Triangles (toggle)
# --------------------------------------------------------------------
class MESH_OT_isolate_triangles(bpy.types.Operator):
    bl_idname = "mesh.isolate_triangles"
    bl_label = "Isolate Triangles"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return toggle_isolate_faces(context, "TRIS")
    
# --------------------------------------------------------------------
# Operator: Isolate Concave (toggle)
# --------------------------------------------------------------------
class MESH_OT_isolate_concave(bpy.types.Operator):
    bl_idname = "mesh.isolate_concave"
    bl_label = "Isolate Concave"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return toggle_isolate_faces(context, "CONCAVE")    

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

        # ------------------------
        # Isolate Section
        # ------------------------
        box = layout.box()
        box.label(text="Isolate", icon='RESTRICT_SELECT_OFF')
        box.prop(context.scene, "show_wire_isolate", text="Show Wireframe")
        box.operator("mesh.isolate_triangles", text="Tris")
        box.operator("mesh.isolate_ngons", text="nGons")
        box.operator("mesh.isolate_non_manifold", text="Non-Manifold")
        box.operator("mesh.isolate_concave", text="Concave")


        # ------------------------
        # Select Section
        # ------------------------
        box = layout.box()
        box.label(text="Select", icon='RESTRICT_SELECT_ON')
        box.operator("mesh.select_tris", text="Triangles")
        box.operator("mesh.select_ngons", text="nGons")
        box.operator("mesh.select_overlapping_vertices", text="Overlapping Verts")
        box.operator("mesh.select_overlapping_faces", text="Overlapping Faces")

        # ------------------------
        # Tris Quads
        # ------------------------
        box = layout.box()
        box.label(text="Geometry", icon='MODIFIER')
        box.operator("mesh.fix_triangulate", text="Triangulate")
        box.operator("mesh.fix_tris_to_quads", text="Tris → Quads")
        if context.mode == 'EDIT_MESH':
            box.operator("mesh.edge_rotate_custom", text="Rotate Edge")

        # ------------------------
        # Fix Section
        # ------------------------
        box = layout.box()
        box.label(text="Fix", icon='MODIFIER')
        box.operator("mesh.fix_ngone", text="nGons")
        box.operator("mesh.cleanup_mesh", text="Cleanup")
            
        # ------------------------
        # Decimate Section
        # ------------------------
        box = layout.box()
        box.label(text="Decimate", icon='MODIFIER')

        # Slider
        box.prop(context.scene, "decimate_angle_limit", text="Angle Limit")

        # Buttons always present
        row = box.row()
        row.operator("mesh.add_planar_decimate", text="Decimate (Planar)")
        box.operator("mesh.apply_planar_decimate", text="Apply Decimate")

        # Update modifier live if it exists
        obj = context.object
        if obj and obj.type == 'MESH':
            dec = obj.modifiers.get("DecimatePlanar")
            if dec:
                dec.angle_limit = radians(context.scene.decimate_angle_limit)


# --------------------------------------------------------------------
# REGISTER
# --------------------------------------------------------------------
classes = (
    MESH_OT_select_ngons,
    MESH_OT_isolate_ngons,
    MESH_OT_isolate_triangles,
    MESH_OT_revert_view,
    MESH_OT_fix_ngone,
    MESH_OT_isolate_non_manifold,
    MESH_OT_isolate_concave,
    MESH_OT_triangulate,
    MESH_OT_tris_to_quads,
    MESH_OT_edge_rotate,
    MESH_OT_select_tris,
    VIEW3D_PT_gaming_toolkit,
    MESH_OT_select_overlapping_vertices,
    MESH_OT_select_overlapping_faces,
    MESH_OT_add_decimate,
    MESH_OT_apply_decimate,
    MESH_OT_cleanup,
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

if __name__ == "__main__":
    register()