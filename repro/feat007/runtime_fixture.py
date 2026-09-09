"""Persistent-framebuffer prerequisite shared by integrated checkpoint probes."""
def initialize_framebuffers(write,call,read,enemy):
    write(0xFFA1,range(0x30,0x34))
    write(0xFFA5,[0x34])
    call(enemy['framebuffer_init_impl'])
    assert read(enemy['FB_INIT_STATE'],1)==bytes([1])
    assert read(enemy['FB_FRONT_ID'],3)==bytes([0,1,0])
