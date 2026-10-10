from runtime import *
def test(q):
 q.capture_audio=True
 q.wait(lambda:q.val('PRES_MODE')==2,'natural attract')
 assert r.read_bytes(q.c,0xc000,0x3e00)==(B/'ladybug-runtime.rom').read_bytes()[:0x3e00]
 attract_hash=hashlib.sha256(q.fb()).hexdigest()
 q.wait(lambda:q.val('PRES_MODE')==4,'natural silent demo')
 states=[]
 for _ in range(100):
  q.go();states.append(list(q.phys(0x3d*8192+q.au['audio_slot0']-0xa000,112)[::28]))
 assert not q.cues and all(all(x==255 for x in s) for s in states),(q.cues,states[:5])
 return {'cold_attract_front_sha256':attract_hash,'natural_demo_samples':len(states),'cue6_admissions':0,'all_voices_idle':True,'resident_identity':True}
receipt('demo-current.json',test)
