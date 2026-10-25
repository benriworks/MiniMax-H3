import bpy,json,hashlib
from pathlib import Path
BASE=Path(__file__).resolve().parent
results={}
for variant in ['initial','thicker_anko']:
 path=BASE/f'dorayaki_{variant}.blend'
 bpy.ops.wm.open_mainfile(filepath=str(path))
 bpy.context.view_layer.update()
 s=bpy.context.scene
 results[variant]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'objects':len(bpy.data.objects),'camera_matrix':[list(r) for r in s.camera.matrix_world],'camera_scale':s.camera.data.ortho_scale,'lights':{o.name: {'energy':o.data.energy,'location':list(o.location)} for o in bpy.data.objects if o.type=='LIGHT'},'parts':{o.name: {'location':list(o.location),'dimensions':list(o.dimensions),'scale':list(o.scale)} for o in bpy.data.objects if any(term in o.name for term in ['pancake','azuki filling','serving plate'])},'view3d_area_count':sum(a.type=='VIEW_3D' for screen in bpy.data.screens for a in screen.areas)}
a,b=results.values()
assert a['camera_matrix']==b['camera_matrix']
assert a['camera_scale']==b['camera_scale']
assert a['lights']==b['lights']
assert a['objects']==b['objects']
for p in ['Dorayaki front','Dorayaki back']:
 assert abs(b['parts'][p+' azuki filling']['dimensions'][2]/a['parts'][p+' azuki filling']['dimensions'][2]-1.3)<1e-5
 assert a['parts'][p+' lower pancake']==b['parts'][p+' lower pancake']
results['checks']={'same_camera_and_lights':True,'same_object_count':True,'anko_thickness_factor':1.3,'lower_pancakes_unchanged':True,'background_reopen_success':True,'gui_reopen':'separate human-visible GUI check required'}
(BASE/'file_verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('VERIFICATION_PASS')
