"""Executed inside the cold-GMC handoff harness after live initialization."""
def put(address, data):
    client.call('write_memory',dict(addr=address,data=bytes(data).hex()))

def quiet_reach(address):
    bp=b.set_breakpoint(client,address)
    try:assert b.run_to_breakpoint(client,10)['pc']==address
    finally:client.call('pause');b.clear_breakpoint(client,bp)

def invoke(address):
    put(0x1800,[0x20,0xFE]);put(0x1FFC,[0x18,0])
    client.call('write_registers',dict(pc=address,s=0x1FFC,dp=0,cc=0x50))
    quiet_reach(0x1800)

def foreground():
    invoke(enemy['framebuffer_irq_impl'])
    put(main['LAST_FRAME'],[0]);put(main['FRAMES'],[0,1])
    client.call('write_registers',dict(pc=main['mainloop']+1,s=0x1FFE,dp=0,cc=0x50))
    start=b.read_timing(client)
    if globals().get('trace_stage',False):
        trace_stage_call()
    else:quiet_reach(main['mainloop'])
    end=b.read_timing(client)
    return end['cpu_cycles']-start['cpu_cycles']

def field_pixels(fields):
    mapping=b.read_bytes(client,0xFFA1,5);differences=[];cells=0
    try:
        for owner in (0,1):
            first=0x30-owner*4;put(0xFFA1,range(first,first+4))
            pixels=b.read_bytes(client,0x2000,30720)
            for x,y,glyphs,colour in fields:
                for index,glyph in enumerate(glyphs):
                    offset=y*1280+(x+index)*4
                    expected=bytes((colour if font[glyph*8+r]&(128>>(j*2)) else 0)*16+(colour if font[glyph*8+r]&(64>>(j*2)) else 0) for r in range(8) for j in range(4))
                    actual=b''.join(pixels[offset+r*160:offset+r*160+4] for r in range(8))
                    cells+=1
                    if actual!=expected:differences.append([owner,x+index,y])
    finally:put(0xFFA1,mapping)
    return cells,differences

print('phase=live-HUD-boundaries marker=mainloop/return1800 deadline=10s per tick; timeout=foreground boundary not reached',flush=True)
identity('resident before HUD event',0xC000,(OUT/'main.bin').read_bytes())
cases=[]
for value in (bytes.fromhex('009990'),bytes.fromhex('999980')):
    # Force numeric boundary only; execute the actual score mutation and its
    # existing RF_HUD trigger, then normal foreground replay on alternating buffers.
    put(main['SCORE_BCD'],value);put(main['MULTIPLIER'],[1])
    invoke(main['add_dot_score'])
    ticks=[foreground() for _ in range(4)]
    score=b.read_bytes(client,main['SCORE_BCD'],3)
    high=b.read_bytes(client,main['HIGH_BCD'],3)
    digits=lambda data:[n for v in data for n in (v>>4,v&15)]
    fields=[(33,2,digits(score),main['COLOR_LIGHT_GREEN']),(33,6,digits(high),main['COLOR_RED'])]
    cells,diff=field_pixels(fields)
    cases.append(dict(input=value.hex(),score=score.hex(),high=high.hex(),ticks=ticks,cells=cells,differences=diff))
    checks.append(dict(label='HUD carry '+value.hex(),exact=not diff and max(ticks)<=27000,evidence=cases[-1]))
    if diff:break

print('phase=live-letter-multiplier-replay marker=mainloop deadline=10s per tick',flush=True)
glyph_cells=(OUT.parent/'fit/asset-text-data.bin').read_bytes()[840:904]
for colour,row in ((main['COLOR_RED'],1),(main['COLOR_YELLOW'],4)):
    put(main['BONUS_COLOR'],[colour]);put(main['ENTITY_VARIANT'],[9 if row==1 else 4])
    invoke(main['apply_letter_pickup'])
    ticks=[foreground() for _ in range(4)]
    cells,diff=field_pixels([(1,row,[glyph_cells[row*8+1]],colour)])
    checks.append(dict(label=f'letter pickup row {row}',exact=not diff and max(ticks)<=27000,cells=cells,differences=diff,ticks=ticks))
for multiplier,x in ((2,1),(3,3),(5,5)):
    # Force the event result and its existing dirty flag; replay remains runtime-owned.
    put(main['MULTIPLIER'],[multiplier])
    flags=b.read_bytes(client,main['RENDER_FLAGS2'],1)[0]
    put(main['RENDER_FLAGS2'],[flags|main['RF2_MULTIPLIER']])
    ticks=[foreground() for _ in range(4)]
    cells,diff=field_pixels([(x,7,list(glyph_cells[56+x:58+x]),main['COLOR_BLUE'])])
    checks.append(dict(label=f'multiplier {multiplier}',exact=not diff and max(ticks)<=27000,cells=cells,differences=diff,ticks=ticks))

print('phase=stage-nine-to-ten marker=live return deadline=10s per tick; cap=300 ticks',flush=True)
if '--stage-profile' in sys.argv:
    exec((OUT.parent/'stage_profile_checks.py').read_text())
    trace_stage=True
put(main['STAGE'],[9]);put(main['STAGE_PENDING'],[1])
stage_ticks=[];saw_panel=False
for tick in range(300):
    cycles=foreground();mode=b.read_bytes(client,pres['PRES_MODE'],1)[0]
    stage_ticks.append(cycles)
    saw_panel |= mode!=0
    if saw_panel and mode==0:break
settle=[foreground() for _ in range(4)]
trace_stage=False
if '--stage-profile' in sys.argv:
    (OUT/'stage-profile.json').write_text(json.dumps(dict(frames=stage_trace,cycles=stage_ticks+settle),indent=2)+'\n')
    compare_stage_baseline()
cells,diff=field_pixels([(38,11,[0],main['COLOR_BLUE']),(35,13,[5,5,0,0],main['COLOR_GREEN'])])
stage_pixels=saw_panel and tick<299 and b.read_bytes(client,main['STAGE'],1)==bytes([10]) and not diff
checks.append(dict(label='stage9 to10 panel/live HUD',exact=stage_pixels and max(stage_ticks+settle)<=27000,pixel_exact=stage_pixels,timing_pass=max(stage_ticks+settle)<=27000,stage=b.read_bytes(client,main['STAGE'],1).hex(),cells=cells,differences=diff,foreground_max=max(stage_ticks+settle),ticks=len(stage_ticks),scope='Forced stage boundary followed by ordinary panel/live progression; single-digit modulo10 HUD and 5500 bonus. Stage setup cost retained separately; baseline attribution required.'))

# Follow the existing terminal-death boundary with a deliberately nonqualifying
# score. No presentation selector or timer is forced; the runtime chooses it.
print('phase=nonqualifying-game-over marker=next screen request deadline=10s per tick; cap=260 foreground ticks',flush=True)
put(main['SCORE_BCD'],[0,0,0]);put(main['DEATH_STATE'],[4])
history=[];next_screen=None
for tick in range(260):
    cycles=foreground()
    screen=b.read_bytes(client,pres['PRES_SCREEN'],1)[0]
    mode=b.read_bytes(client,pres['PRES_MODE'],1)[0]
    history.append(dict(tick=tick,screen=screen,mode=mode,cycles=cycles))
    if tick==0:identity('game-over auxiliary owner',0x300,(OUT/'highscore.bin').read_bytes())
    if screen!=4 and tick>0:
        next_screen=screen;break
checks.append(dict(label='nonqualifying game-over skips name entry',exact=next_screen in (0,3),actual_next_screen=next_screen,scope='Forced terminal death and zero score, then unforced runtime screen/timer progression.',history=history))
