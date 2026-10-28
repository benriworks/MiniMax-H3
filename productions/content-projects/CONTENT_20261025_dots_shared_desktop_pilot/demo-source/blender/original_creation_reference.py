import bpy, math, random
from pathlib import Path
BASE=Path(__file__).resolve().parent
from mathutils import Vector
random.seed(14)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
for d in bpy.data.materials: bpy.data.materials.remove(d)

def mat(name,color,rough=.5):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough
 return m

def food(name,c1,c2,scale,bump):
 m=mat(name,c1);n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF')
 t=n.new('ShaderNodeTexNoise');t.inputs['Scale'].default_value=scale;t.inputs['Detail'].default_value=3;t.inputs['Roughness'].default_value=.75
 r=n.new('ShaderNodeValToRGB');r.color_ramp.elements[0].position=.2;r.color_ramp.elements[0].color=(*c1,1);r.color_ramp.elements[1].position=.8;r.color_ramp.elements[1].color=(*c2,1)
 l.new(t.outputs['Fac'],r.inputs[0]);l.new(r.outputs[0],p.inputs['Base Color'])
 fine=n.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=160;fine.inputs['Detail'].default_value=2
 b=n.new('ShaderNodeBump');b.inputs['Strength'].default_value=.28;b.inputs['Distance'].default_value=bump;l.new(fine.outputs['Fac'],b.inputs['Height']);l.new(b.outputs[0],p.inputs['Normal'])
 p.inputs['Subsurface Weight'].default_value=.045
 return m
brown=food('Honey golden toasted pancake',(.24,.068,.013),(.64,.285,.065),5,.023)
rim=food('Soft golden sponge edge',(.57,.285,.09),(.93,.65,.3),11,.025)
anko=food('Glossy burgundy azuki paste',(.022,.004,.006),(.12,.026,.025),18,.05)
anko.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.31
ceramic=food('Celadon ceramic glaze',(.095,.22,.20),(.15,.31,.28),8,.006)
ceramic.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.21

def lathe(name,profile,mats,loc=(0,0,0),irregular=0,segments=128):
 v=[];f=[]
 for j,(r,z) in enumerate(profile):
  for i in range(segments):
   a=2*math.pi*i/segments;rr=r*(1+irregular*(.5*math.sin(a*5)+.3*math.cos(a*9)))
   v.append((rr*math.cos(a),rr*math.sin(a),z+irregular*.2*math.sin(a*7)*min(r,1)))
 for j in range(len(profile)-1):
  for i in range(segments): f.append((j*segments+i,j*segments+(i+1)%segments,(j+1)*segments+(i+1)%segments,(j+1)*segments+i))
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(v,[],f);mesh.update();ob=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(ob);ob.location=loc
 for m in mats: ob.data.materials.append(m)
 for p in mesh.polygons:p.use_smooth=True
 return ob
# Plate profile runs from underside to inner bowl, making a solid ceramic dish.
plate=lathe('Hand-thrown celadon serving plate',[(0,.06),(1.5,.06),(1.58,.08),(1.6,.12),(2.4,.15),(2.65,.24),(2.72,.30),(2.70,.35),(2.64,.36),(2.43,.27),(2.1,.19),(1.6,.17),(0,.17)],[ceramic])

def pancake(name,loc,flip=False):
 profile=[(0,-.13),(.65,-.13),(1.02,-.115),(1.12,-.08),(1.17,-.02),(1.18,.025),(1.15,.09),(1.08,.145),(.94,.19),(.72,.225),(.4,.245),(0,.25)]
 ob=lathe(name,profile,[brown,rim],loc,.012)
 for p in ob.data.polygons:
  j=p.index//128;p.material_index=1 if j in (2,3,4,5) else 0
 if flip: ob.rotation_euler.x=math.pi
 return ob

def dorayaki(name,x,y,z,angle):
 parts=[]
 parts.append(pancake(name+' lower pancake',(0,0,.19),True))
 filling=lathe(name+' azuki filling',[(0,-.12),(.85,-.12),(1.05,-.09),(1.12,-.02),(1.11,.06),(.99,.13),(0,.13)],[anko],(0,0,.41),.026);parts.append(filling)
 parts.append(pancake(name+' upper pancake',(0,0,.59)))
 for i in range(70):
  a=random.uniform(0,math.tau);r=random.uniform(1.025,1.1); zz=.41+random.uniform(-.065,.06)
  bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,location=(r*math.cos(a),r*math.sin(a),zz));o=bpy.context.object;o.name=name+' azuki bean';o.scale=(random.uniform(.035,.075),random.uniform(.025,.055),random.uniform(.023,.045));o.data.materials.append(anko)
  for p in o.data.polygons:p.use_smooth=True
  parts.append(o)
 root=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(root)
 for p in parts:p.parent=root
 root.location=(x,y,z);root.rotation_euler=(0,0,angle)
 return root
# Two individual sweets, slightly overlapping in the presentation.
dorayaki('Dorayaki front',-.48,-.65,.36,-.12)
dorayaki('Dorayaki back',.55,.77,.43,.2)
# A scattering of soft cake crumbs on the plate.
for i in range(14):
 a=random.uniform(0,math.tau);r=random.uniform(1.65,2.18)
 bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=random.uniform(.015,.032),location=(r*math.cos(a),r*math.sin(a),.235));bpy.context.object.name='Pancake crumb';bpy.context.object.scale.z=.55;bpy.context.object.data.materials.append(rim)
backdrop=mat('Warm linen backdrop',(.48,.36,.255),.85)
bpy.ops.mesh.primitive_plane_add(size=200);bpy.context.object.name='Matte warm studio surface';bpy.context.object.data.materials.append(backdrop)
# Small indigo linen napkin beside plate, restrained editorial styling.
napkin=food('Indigo linen',(.025,.054,.07),(.055,.098,.115),12,.014)
bpy.ops.mesh.primitive_cube_add(size=1,location=(-2.25,1.0,.035));o=bpy.context.object;o.name='Folded indigo linen';o.scale=(1.6,2.7,.055);o.rotation_euler.z=.24;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(napkin);mod=o.modifiers.new('Soft folded edges','BEVEL');mod.width=.07;mod.segments=4;o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')

def aim(obj,pt):obj.rotation_euler=(Vector(pt)-obj.location).to_track_quat('-Z','Y').to_euler()
def light(name,pos,power,size,color):
 bpy.ops.object.light_add(type='AREA',location=pos);o=bpy.context.object;o.name=name;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.data.color=color;aim(o,(0,0,.4))
light('Large softbox left',(-3,-4,7),750,5,(1,.87,.7));light('Soft cool fill',(4,1,5),450,4,(.78,.87,1));light('Warm rim',(-1,5,5),550,3,(1,.8,.57))
bpy.ops.object.camera_add(location=(5,-8,6.5));cam=bpy.context.object;cam.name='Editorial food camera';aim(cam,(0,0,.45));cam.data.type='ORTHO';cam.data.ortho_scale=6.9;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=48;scene.cycles.use_denoising=True;scene.render.resolution_x=1400;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.world.color=(.25,.25,.25);scene.view_settings.view_transform='AgX'
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(BASE/'source_scene.png')
for area in bpy.context.screen.areas:
 if area.type=='VIEW_3D':
  area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.shading.type='MATERIAL'
bpy.ops.wm.save_as_mainfile(filepath=str(BASE/'source_scene.blend'))
bpy.ops.render.render(write_still=True)
