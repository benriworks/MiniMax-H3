import bpy,json,hashlib
from pathlib import Path
from mathutils import Vector
BASE=Path(__file__).resolve().parent
SOURCE=BASE/'source_scene.blend'
source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene=bpy.context.scene
scene.render.threads_mode='FIXED';scene.render.threads=4
scene.cycles.samples=48
scene.cycles.seed=14
scene.render.resolution_x=1400;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
# Save a genuinely interactive 3D viewport, not an image-only editor.
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':
   space=area.spaces.active
   space.shading.type='SOLID';space.shading.color_type='MATERIAL'
   space.overlay.show_overlays=False
   space.region_3d.view_perspective='CAMERA'
   space.region_3d.view_camera_zoom=0
   space.region_3d.view_location=(0,0,.5)
   space.region_3d.view_distance=8
bpy.ops.object.select_all(action='DESELECT')
obj=bpy.data.objects['Dorayaki front upper pancake'];obj.select_set(True);bpy.context.view_layer.objects.active=obj
scene['demo_environment']='Fictional filming demo. No real services.'
scene['variant']='Initial copied scene'
scene.render.filepath=str(BASE/'dorayaki_initial.png')
bpy.ops.wm.save_as_mainfile(filepath=str(BASE/'dorayaki_initial.blend'))
initial={}
for prefix in ['Dorayaki front','Dorayaki back']:
 f=bpy.data.objects[prefix+' azuki filling']
 initial[prefix]={'filling_local_z':f.location.z,'filling_scale_z':f.scale.z,'filling_mesh_z_min':min(v.co.z for v in f.data.vertices),'filling_mesh_z_max':max(v.co.z for v in f.data.vertices),'upper_z':bpy.data.objects[prefix+' upper pancake'].location.z}
# Expand the filling 30% about its lower face, moving the upper cake by the same
# top-face displacement. Bean positions and vertical scales follow the filling.
changes={}
for prefix in initial:
 info=initial[prefix];f=bpy.data.objects[prefix+' azuki filling'];bottom=info['filling_local_z']+info['filling_mesh_z_min'];height=info['filling_mesh_z_max']-info['filling_mesh_z_min'];rise=height*.30
 f.scale.z*=1.30;f.location.z=bottom+(info['filling_local_z']-bottom)*1.30
 top=bpy.data.objects[prefix+' upper pancake'];top.location.z+=rise
 for o in bpy.data.objects:
  if o.name.startswith(prefix+' azuki bean'):
   o.location.z=bottom+(o.location.z-bottom)*1.30;o.scale.z*=1.30
 changes[prefix]={'factor':1.30,'initial_height':height,'modified_height':height*1.30,'top_rise':rise,'upper_z_before':info['upper_z'],'upper_z_after':top.location.z,'lower_face_unchanged':True}
scene['variant']='Anko +30% thickness; upper cakes moved upward'
scene.render.filepath=str(BASE/'dorayaki_thicker_anko.png')
bpy.ops.wm.save_as_mainfile(filepath=str(BASE/'dorayaki_thicker_anko.blend'))
report={'blender_version':bpy.app.version_string,'source_sha256_before':source_hash,'changes':changes,'same_camera':True,'camera_location':list(scene.camera.location),'camera_rotation':list(scene.camera.rotation_euler),'camera_ortho_scale':scene.camera.data.ortho_scale,'render_resolution':[1400,1100],'cycles_samples':48,'gui_checks':'Not performed by file generation; separate GUI verification required.'}
(BASE/'variant_metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('BOTH_BLEND_FILES_READY',flush=True)
for variant in ['initial','thicker_anko']:
 bpy.ops.wm.open_mainfile(filepath=str(BASE/f'dorayaki_{variant}.blend'))
 bpy.ops.render.render(write_still=True)
 print('RENDER_DONE',variant,flush=True)
report['source_sha256_after']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
assert report['source_sha256_before']==report['source_sha256_after']
report['render_files']=['dorayaki_initial.png','dorayaki_thicker_anko.png']
(BASE/'variant_metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
