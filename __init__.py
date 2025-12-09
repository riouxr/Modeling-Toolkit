bl_info = {
    "name": "Gaming toolkit",
    "category": "Mesh",
    "author": "Blender Bob",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > N panel > Gaming toolkit",
    "description": "Most used tools when modeling for gaming",
}

import bpy
import bmesh

# --------------------------------------------------------------------
# Helper: detect n-gons and select faces
# --------------------------------------------------------------------
def select_ngons(obj):
    me = obj.data
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select = len(f.verts) > 4
    bmesh.update_edit_mesh(me)


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
# Operator: Isolate n-gons
# --------------------------------------------------------------------
class MESH_OT_isolate_ngons(bpy.types.Operator):
    bl_idname = "mesh.isolate_ngons"
    bl_label = "Isolate nGons"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        # Object mode to safely hide
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for f in obj.data.polygons:
            f.hide = False if len(f.vertices) > 4 else True

        bpy.ops.object.mode_set(mode='EDIT')
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

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for f in obj.data.polygons:
            f.hide = False

        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


# --------------------------------------------------------------------
# Operator: Fix nGones
# --------------------------------------------------------------------
class MESH_OT_fix_ngone(bpy.types.Operator):
    bl_idname = "mesh.fix_ngone"
    bl_label = "Fix nGones"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        select_ngons(obj)
        bpy.ops.mesh.select_all(action='SELECT')
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
            # Edit mode: only selected polygons
            bpy.ops.mesh.quads_convert_to_tris()
        else:
            # Object mode: select all and triangulate
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
    bl_label = "Rotate"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.edge_rotate(use_ccw=True)
        return {'FINISHED'}


# --------------------------------------------------------------------
# PANEL
# --------------------------------------------------------------------
class VIEW3D_PT_gaming_toolkit(bpy.types.Panel):
    bl_label = "Gaming Toolkit"
    bl_category = "Tool"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout

        layout.operator("mesh.select_ngons", text="Select nGons")
        layout.operator("mesh.isolate_ngons", text="Isolate nGons")
        layout.operator("mesh.revert_view", text="Revert View")

        layout.separator()
        layout.operator("mesh.fix_ngone", text="Fix nGone")

        layout.separator()
        layout.operator("mesh.fix_triangulate", text="Triangulate")
        layout.operator("mesh.fix_tris_to_quads", text="Tris → Quads")

        layout.separator()
        # Show Rotate only in Edit Mode
        if context.mode == 'EDIT_MESH':
            layout.operator("mesh.edge_rotate_custom", text="Rotate")




# --------------------------------------------------------------------
# REGISTER
# --------------------------------------------------------------------
classes = (
    MESH_OT_select_ngons,
    MESH_OT_isolate_ngons,
    MESH_OT_revert_view,
    MESH_OT_fix_ngone,
    MESH_OT_triangulate,
    MESH_OT_tris_to_quads,
    MESH_OT_edge_rotate,
    VIEW3D_PT_gaming_toolkit,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
