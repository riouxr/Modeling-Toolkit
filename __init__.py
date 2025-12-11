bl_info = {
    "name": "Convert to Gaming",
    "author": "Your Name",
    "version": (1, 3),
    "blender": (2, 80, 0),
    "location": "View3D > UI > Tool",
    "description": "Converts high-poly objects to low-poly for gaming",
    "category": "Object",
}

import bpy
import bmesh
from math import radians, pi

HIGH_COLL = "High"
LOW_COLL = "Low"

# ---------------------------------------------------
# Helpers (with prints)
# ---------------------------------------------------

def ensure_collection(name):
    col = bpy.data.collections.get(name)
    if not col:
        print(f"[COLLECTION] Creating collection '{name}'")
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    else:
        print(f"[COLLECTION] Found collection '{name}'")
    return col

def select_only(obj):
    # ensure object mode
    if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def apply_modifier_safe(obj, mod_name):
    select_only(obj)
    try:
        bpy.ops.object.modifier_apply(modifier=mod_name)
        print(f"    [APPLY] Successfully applied modifier '{mod_name}' on '{obj.name}'")
        return True
    except Exception as e:
        print(f"    [APPLY] Failed to apply modifier '{mod_name}' on '{obj.name}': {e}")
        return False

# safe remove that logs
def remove_modifier_safe(obj, m):
    # store name and type first
    mod_name = m.name
    mod_type = m.type
    try:
        obj.modifiers.remove(m)
        print(f"    [REMOVE] Removed modifier '{mod_name}' (type={mod_type}) from '{obj.name}'")
        return True
    except Exception as e:
        print(f"    [REMOVE] Failed to remove modifier '{mod_name}' on '{obj.name}': {e}")
        return False

# ---------------------------------------------------
# Processing for each Low object - Part 1: Prep modifiers without applying decimate
# ---------------------------------------------------

def process_low_prep(obj):
    print(f"\n=== Prepping object: '{obj.name}' ===")

    # Rename
    original_name = obj.name
    if not obj.name.endswith("_low"):
        obj.name = obj.name + "_low"
        print(f"[RENAME] '{original_name}' -> '{obj.name}'")
    else:
        print(f"[RENAME] Already named '{obj.name}'")

    # Print current modifiers
    mods_before = [(m.name, m.type) for m in obj.modifiers]
    print(f"[MODS] Before: {mods_before if mods_before else 'None'}")

    # Remove Subsurf + Smooth
    for m in list(obj.modifiers):
        if m.type in {"SUBSURF", "SMOOTH"}:
            remove_modifier_safe(obj, m)

    # Show modifiers after removing subsurf/smooth
    mods_mid = [(m.name, m.type) for m in obj.modifiers]
    print(f"[MODS] After removing Subsurf/Smooth: {mods_mid if mods_mid else 'None'}")

    # Apply Mirror + Bevel
    for m in list(obj.modifiers):
        if m.type in {"MIRROR", "BEVEL"}:
            mod_name = m.name
            print(f"    [APPLY_REQUEST] Applying {m.type} '{mod_name}' on '{obj.name}'")
            applied = apply_modifier_safe(obj, mod_name)
            if not applied:
                print(f"    [APPLY_REQUEST] Could not apply '{mod_name}' — continuing")

    # Show modifiers after applying Mirror+Bevel
    mods_after_apply = [(m.name, m.type) for m in obj.modifiers]
    print(f"[MODS] After applying Mirror/Bevel: {mods_after_apply if mods_after_apply else 'None'}")

    # Remove ANY existing Decimate modifiers
    decs = [m for m in list(obj.modifiers) if m.type == 'DECIMATE']
    if decs:
        print(f"[DECI] Found existing DECIMATE modifiers: {[(d.name, d.decimate_type if hasattr(d, 'decimate_type') else 'N/A') for d in decs]}")
    for m in decs:
        remove_modifier_safe(obj, m)

    # Add fresh Planar Decimate (using 'DISSOLVE' for Blender 4.1+)
    dec = None
    try:
        dec = obj.modifiers.new(name="DecimatePlanar", type="DECIMATE")
        dec.decimate_type = 'DISSOLVE'
        dec.angle_limit = radians(0.5)
        dec.delimit = {'NORMAL'}
        print(f"[DECI] Added new DISSOLVE (Planar) decimate 'DecimatePlanar' on '{obj.name}' with angle_limit=0.5° and delimit=Normal")
    except Exception as e:
        print(f"[DECI] Failed to add/set DISSOLVE decimate on '{obj.name}': {e}")
        dec = None

    # Do NOT apply here

    # Final modifiers list after prep
    mods_final = [(m.name, m.type) for m in obj.modifiers]
    print(f"[MODS] Modifiers after prep on '{obj.name}': {mods_final if mods_final else 'None'}")

# ---------------------------------------------------
# Processing for each Low object - Part 2: Apply decimate
# ---------------------------------------------------

def process_low_apply_decimate(obj):
    print(f"\n=== Applying decimate on object: '{obj.name}' ===")

    # Find and apply the decimate modifier
    dec_mod = None
    for m in obj.modifiers:
        if m.type == 'DECIMATE' and m.decimate_type == 'DISSOLVE':
            dec_mod = m
            break

    if dec_mod:
        apply_modifier_safe(obj, dec_mod.name)
    else:
        print(f"[DECI] No DISSOLVE decimate modifier found on '{obj.name}' to apply")

    # Final modifiers list after apply
    mods_final = [(m.name, m.type) for m in obj.modifiers]
    print(f"[MODS] Modifiers after applying decimate on '{obj.name}': {mods_final if mods_final else 'None'}")

# ---------------------------------------------------
# Geometry Operations: Select Ngons > 5 edges (with logging)
# ---------------------------------------------------

def edit_triangulate_to_quads(obj):

    if obj.type != 'MESH':
        print(f"[GEOM] Skipping '{obj.name}' (not a mesh)")
        return

    print(f"[GEOM] Starting geometry ops on '{obj.name}'")
    select_only(obj)
    try:
        bpy.ops.object.mode_set(mode='EDIT')
    except Exception as e:
        print(f"    [GEOM] Failed to enter EDIT mode for '{obj.name}': {e}")
        return

    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    # Deselect all faces
    for f in bm.faces:
        f.select = False

    # Select ngons with > 5 verts
    ngons = [f for f in bm.faces if len(f.verts) > 5]
    print(f"    [GEOM] Found {len(ngons)} ngon(s) (>5 edges) in '{obj.name}'")
    for f in ngons:
        f.select = True

    bmesh.update_edit_mesh(obj.data)

    # Triangulate selected ngons using bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    sel_faces = [f for f in bm.faces if f.select]
    if sel_faces:
        try:
            bmesh.ops.triangulate(
                bm,
                faces=sel_faces,
                quad_method='BEAUTY',
                ngon_method='BEAUTY'
            )
            print(f"    [GEOM] Triangulated {len(sel_faces)} selected face(s) on '{obj.name}'")
        except Exception as e:
            print(f"    [GEOM] bmesh triangulate failed on '{obj.name}': {e}")
    else:
        print(f"    [GEOM] No selected faces to triangulate on '{obj.name}'")

    bmesh.update_edit_mesh(obj.data)

    # Select all faces for tris to quads
    try:
        bpy.ops.mesh.select_all(action='SELECT')
        print(f"    [GEOM] Selected all faces for tris_convert_to_quads on '{obj.name}'")
    except Exception as e:
        print(f"    [GEOM] Failed to select all on '{obj.name}': {e}")

    # Convert tris -> quads where possible, with relaxed thresholds and no limits
    try:
        bpy.ops.mesh.tris_convert_to_quads(
            face_threshold=pi,
            shape_threshold=pi,
            uvs=False,
            vcols=False,
            seam=False,
            sharp=False,
            materials=False
        )
        print(f"    [GEOM] Ran tris_convert_to_quads on '{obj.name}' with relaxed parameters")
    except Exception as e:
        print(f"    [GEOM] tris_convert_to_quads failed on '{obj.name}': {e}")

    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception as e:
        print(f"    [GEOM] Failed to exit EDIT mode for '{obj.name}': {e}")

# ---------------------------------------------------
# Main for Convert: Dupe, prep modifiers, hide high
# ---------------------------------------------------

def convert_main():
    print("=== Convert started ===")
    high = bpy.data.collections.get(HIGH_COLL)
    if not high:
        print(f"[ERROR] High collection '{HIGH_COLL}' not found. Aborting.")
        return
    else:
        print(f"[FOUND] High collection '{HIGH_COLL}' has {len(high.objects)} object(s).")

    low = ensure_collection(LOW_COLL)

    # Duplicate objects from High → Low
    new_objects = []
    for src in high.objects:
        print(f"[DUP] Duplicating '{src.name}'...")
        try:
            new_obj = src.copy()
            if src.data:
                try:
                    new_obj.data = src.data.copy()
                    print(f"    [DUP] Copied mesh/data for '{src.name}'")
                except Exception as e:
                    new_obj.data = src.data
                    print(f"    [DUP] Could not copy data for '{src.name}', linked instead: {e}")
            low.objects.link(new_obj)
            new_objects.append(new_obj)
            print(f"    [DUP] Linked duplicate '{new_obj.name}' into '{LOW_COLL}'")
        except Exception as e:
            print(f"    [DUP] Failed to duplicate '{src.name}': {e}")

    print(f"[DUP] Completed duplication. {len(new_objects)} new object(s) in '{LOW_COLL}'.")

    # Prep modifiers on Low objects (without applying decimate)
    for obj in new_objects:
        process_low_prep(obj)

    # Make High collection invisible
    try:
        high.hide_viewport = True
        print(f"[HIDE] Set '{HIGH_COLL}' collection to invisible in viewport")
    except Exception as e:
        print(f"[HIDE] Failed to hide '{HIGH_COLL}': {e}")

    print("=== Convert finished ===")

# ---------------------------------------------------
# Main for Fix nGones: Apply decimate, geometry ops
# ---------------------------------------------------

def fix_ngons_main():
    print("=== Fix nGones started ===")
    low = bpy.data.collections.get(LOW_COLL)
    if not low:
        print(f"[ERROR] Low collection '{LOW_COLL}' not found. Aborting.")
        return
    else:
        print(f"[FOUND] Low collection '{LOW_COLL}' has {len(low.objects)} object(s).")

    low_objects = [obj for obj in low.objects if obj.type == 'MESH']

    # Apply decimate on Low objects
    for obj in low_objects:
        process_low_apply_decimate(obj)

    # Geometry operations on Low objects
    for obj in low_objects:
        edit_triangulate_to_quads(obj)

    print("=== Fix nGones finished ===")

# Operator for Convert
class ConvertOperator(bpy.types.Operator):
    bl_idname = "object.convert_to_gaming"
    bl_label = "Convert"
    bl_description = "Duplicate and prep low-poly objects, hide High"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        convert_main()
        return {'FINISHED'}

# Operator for Fix nGones
class FixNgonsOperator(bpy.types.Operator):
    bl_idname = "object.fix_ngons"
    bl_label = "Fix nGones"
    bl_description = "Apply dissolve decimate and fix ngons on low-poly objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        fix_ngons_main()
        return {'FINISHED'}

# Panel in the N-panel (UI sidebar)
class ConvertToGamingPanel(bpy.types.Panel):
    bl_label = "Convert to Gaming"
    bl_idname = "VIEW3D_PT_convert_to_gaming"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"

    def draw(self, context):
        layout = self.layout
        layout.operator(ConvertOperator.bl_idname)
        layout.operator(FixNgonsOperator.bl_idname)

def register():
    bpy.utils.register_class(ConvertOperator)
    bpy.utils.register_class(FixNgonsOperator)
    bpy.utils.register_class(ConvertToGamingPanel)

def unregister():
    bpy.utils.unregister_class(ConvertToGamingPanel)
    bpy.utils.unregister_class(FixNgonsOperator)
    bpy.utils.unregister_class(ConvertOperator)

if __name__ == "__main__":
    register()