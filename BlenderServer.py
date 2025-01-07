import bpy

import os, sys, select, time, pickle
from multiprocessing import shared_memory

sys.path.append('dummypath')
from BlenderState import BlenderState, Object, Material
from Connection import Connection

POLL_TIME = 0.2

def pollCommand():
    # Poll for new message
    recivedMsg = connection.pollingRecive()
    # If theres no new messages, retrigger poll timer
    if recivedMsg == b'': return POLL_TIME
    # Otherwise extract the command and arguments from the message
    parts = recivedMsg.decode().split(':')
    command = parts[0]
    arguments = parts[1:]
    # Handle the quit command as a seperate case since it
    # doesnt return poll time (to kill the timer)
    if command == 'quit':
        connection.blockingSend("True:".encode())
        connection.blockingSend("Quitting...".encode())
        connection.deinit()
        try: sharedMemoryManager.close()
        except: pass
        try: sharedMemoryManager.unlink()
        except: pass
        return None
    try:
        responseStatus = b'True'
        responseData = b''
        if command == 'sync_state':
            syncedState.clear()
            syncedState.sceneIDs = [scene.name for scene in bpy.data.scenes]
            for sceneID in syncedState.sceneIDs:
                syncedState.sceneObjIDs[sceneID] = [obj.name for obj in bpy.data.scenes[sceneID].objects if obj.type == 'MESH']
                syncedState.sceneObjs[sceneID] = {}
                for objID in syncedState.sceneObjIDs[sceneID]:
                    obj = bpy.data.scenes[sceneID].objects[objID]
                    mesh = obj.data
                    uvLayer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
                    if uvLayer != None: mesh.calc_tangents()
                    colorLayer = mesh.vertex_colors.active if mesh.vertex_colors else None
                    pos = (obj.location.x, obj.location.y, obj.location.z)
                    rot = (obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z)
                    verts = [(v.co[0], v.co[1], v.co[2]) for v in mesh.vertices]
                    polys = []
                    norms = []
                    mats = []
                    uvs = []
                    tans = []
                    colors = []
                    for poly in mesh.polygons:
                        polys.append([vert for vert in poly.vertices])
                        rawNorms = [mesh.loops[i].normal for i in poly.loop_indices]
                        norms.append([(n[0], n[1], n[2]) for n in rawNorms])
                        matIndex = poly.material_index
                        matName = obj.material_slots[matIndex].material.name
                        mats.append(matName)
                        if uvLayer != None:
                            rawUVs = [uvLayer[i].uv for i in poly.loop_indices]
                            uvs.append([(uv[0], uv[1]) for uv in rawUVs])
                            rawTans = [mesh.loops[i].tangent for i in poly.loop_indices]
                            tans.append([(t[0], t[1], t[2]) for t in rawTans])
                        if colorLayer != None:
                            rawColors = [colorLayer.data[i].color for i in poly.loop_indices]
                            colors.append([(c[0], c[1], c[2]) for c in rawColors])
                    syncedState.sceneObjs[sceneID][objID] = Object(pos, rot, verts, polys, mats, norms, colors, uvs, tans)
            syncedState.matIDs = [mat.name for mat in bpy.data.materials]
            for matID in syncedState.matIDs:
                mat = bpy.data.materials[matID]
                texturePath = ''
                if mat.use_nodes:
                    for node in mat.node_tree.nodes:
                        if isinstance(node, bpy.types.ShaderNodeTexImage) and node.image:
                            texturePath = os.path.abspath(node.image.filepath_raw)
                            break
                normalPath = ''
                #for node in mat.node_tree.nodes:
                #    if isinstance(node, bpy.types.ShaderNodeTexImage):
                #        if node.image: normalPath = os.path.abspath(node.image.filepath_raw)
                #        else: break
                syncedState.mats[matID] = Material(texturePath, normalPath)
            pickledState = pickle.dumps(syncedState)
            try:
                sharedMemoryManager = shared_memory.SharedMemory(name = 'BlenderPSXPlusStudio', create=True, size=len(pickledState))
            except:
                sharedMemoryManager = shared_memory.SharedMemory(name = 'BlenderPSXPlusStudio')
                sharedMemoryManager.unlink()
                sharedMemoryManager = shared_memory.SharedMemory(name = 'BlenderPSXPlusStudio', create=True, size=len(pickledState))
            sharedMemoryManager.buf[:len(pickledState)] = pickledState
            responseData = str(len(pickledState)).encode()
        elif command == 'sync_close':
            try: sharedMemoryManager.close()
            except: pass
            try: sharedMemoryManager.unlink()
            except: pass
            responseData = b'Done'
        else:
            responseStatus = b'False'
            responseData = f"Unknown command {command}!".encode()
    except Exception as e:
        responseStatus = b'False'
        responseData = f"Internal error with command {command}! {e}".encode()
    connection.blockingSend(responseStatus + b':' + responseData)
    return POLL_TIME

if __name__ == '__main__':
    inPipePath = "/tmp/P2B"
    outPipePath = "/tmp/B2P"
    syncedState = BlenderState()
    pickledState = None
    sharedMemoryManager = None
    connection = Connection(inPipePath, outPipePath, True)
    bpy.app.timers.register(pollCommand)
