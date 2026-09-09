"""Remaining numeric maximum and non-name ranking-return fixture."""
print('phase=exact-score-maximum marker=mainloop deadline=10s per foreground',flush=True)
put(main['SCORE_BCD'],[0x99]*3);put(main['HIGH_BCD'],[0x99]*3)
put(main['RENDER_FLAGS'],[b.read_bytes(client,main['RENDER_FLAGS'],1)[0]|main['RF_HUD']])
costs=[foreground() for _ in range(4)]
cells,diff=field_pixels([(33,2,[9]*6,main['COLOR_LIGHT_GREEN']),(33,6,[9]*6,main['COLOR_RED'])])
checks.append(dict(label='exact999999 both HUDs and framebuffers',exact=not diff and max(costs)<=27000,cells=cells,differences=diff,cycles=costs))
print('phase=credit-cap marker=return1800 deadline=10s',flush=True)
put(pres['PRES_CREDITS'],[8]);invoke(pres['add_credit']);first=b.read_bytes(client,pres['PRES_CREDITS'],1)[0]
invoke(pres['add_credit']);second=b.read_bytes(client,pres['PRES_CREDITS'],1)[0]
checks.append(dict(label='credit8 to9 saturates9',exact=(first,second)==(9,9),values=[first,second],scope='Actual add_credit routine; credits are graphic slots, not text digits.'))
# Actual keyboard request after restoring IRQ-enabled foreground execution.
client.call('write_registers',dict(pc=main['mainloop'],s=0x1FFE,dp=0,cc=0))
client.call('inject_key',dict(key=5,action='press'));reach('credit-from-live',pres['start_screen'])
checks.append(dict(label='credit from live requests ranking',exact=client.call('read_registers')['a']==3))
client.call('inject_key',dict(key=5,action='release'))
reach('ranking-return-entry',main['mainloop'])
print('phase=ranking-natural-timeout marker=title request deadline=10s; no forced timer',flush=True)
reach('ranking-timeout-title',pres['start_screen'])
checks.append(dict(label='ranking timeout requests title',exact=client.call('read_registers')['a']==0))
reach('title-reentry-mainloop',main['mainloop'])
identity('instruction owner restored on title return',0x300,(OUT/'instruction.bin').read_bytes())
