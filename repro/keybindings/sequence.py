        defaults=[27,35,43,51,6,44,12]
        assert list(r.read_bytes(client,0x0287,7))==defaults
        key(0x30,6);options_pixels(0)
        key(0x2E,6);assert read(0xEA)==4;options_pixels(0)
        key(0x2C,6);key(0x2E,6);assert read(0xEB)==2;options_pixels(1)
        key(0x2C,6);assert read(0xE0)==2;options_pixels(2)
        key(0x30,8);assert read(0xE0)==0
        def base(screen):
            cold=(BUILD/'ladybug-presentation-cold.bin').read_bytes();ptr=manifest['map_stream_offsets'][screen];cell=0;frame=bytearray(30720)
            while cell<960:
                count,glyph=cold[ptr:ptr+2];ptr+=2
                if glyph>=174:
                    colour=cold[ptr];ptr+=1;mask=font[(glyph-174)*8:(glyph-174+1)*8]
                    tile=bytes((colour if mask[y]&(128>>(j*2)) else 0)*16+(colour if mask[y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4))
                else:tile=cold[glyph*32:glyph*32+32]
                for _ in range(count):
                    at=(cell//40)*1280+(cell%40)*4
                    for y in range(8):frame[at+y*160:at+y*160+4]=tile[y*4:y*4+4]
                    cell+=1
            return frame
        keybase=base(8);kp=ROOT/'tiled/coco-keybind-options-screen.tmx';kr,kflat,_=shared.p.flatten_map(kp)
        rows=manifest['menus']['keybindings']['action_rows'];back=manifest['menus']['keybindings']['back_row']
        # Independent physical legends in CoCo PA-row order, not runtime name records.
        legends=['@ABCDEFG','HIJKLMNO','PQRSTUVW',['X','Y','Z','UP ARROW','DOWN ARROW','LEFT ARROW','RIGHT ARROW','SPACE'],'01234567',['8','9','COLON','SEMICOLON','COMMA','MINUS','PERIOD','SLASH'],['ENTER','CLEAR','BREAK','ALT','CONTROL','F1','F2','SHIFT']]
        def legend(code):
            word=legends[code%8][code//8]
            return 'AT' if word=='@' else word
        def kexpected():
            frame=bytearray(keybase);sel=read(0xE0);state=read(0x0298)
            for i,row in enumerate(rows+[back]):
                colour=10 if i==sel else 7
                for col in range(23 if i==7 else 18):
                    code=shared.p.raw_char_code(kr,kp,kflat[row*40+col])
                    if code is not None and code<=35:paint(frame,0x2000+row*1280+col*4,code,colour)
                if i==7:continue
                for col in range(19,33):paint(frame,0x2000+row*1280+col*4,36,colour)
                word=legend(read(0x0287+i));lo=32-len(word)
                for offset,ch in enumerate(word):paint(frame,0x2000+row*1280+(lo+offset)*4,36 if ch==' ' else int(ch) if ch.isdigit() else ord(ch)-55,colour)
                if i==sel and state in (1,2):
                    paint(frame,0x2000+row*1280+(lo-1)*4,43,colour);paint(frame,0x2000+row*1280+32*4,44,colour)
            return bytes(frame)
        def pixels(label):
            ready(8);expected=kexpected()
            for owner in (0,1):assert r.read_owner(client,owner)==expected,(label,owner,read(0xE0),read(0x0298))
            check('keybinding both-owner pixels '+label,r.digest(expected))
        def pick(index):
            while read(0xE0)!=index:key(0x2B if read(0xE0)>index else 0x2C,8)
        select=0x30
        def opening(label):
            credits=read(0xA8);old=list(r.read_bytes(client,0x0287,7))
            client.call('inject_key',{'key':select,'action':'press'})
            for _ in range(8):tick()
            assert read(0x0298)==1 and list(r.read_bytes(client,0x0287,7))==old
            pixels(label+' activating key held')
            client.call('inject_key',{'key':select,'action':'release'})
            for _ in range(4):tick()
            assert read(0x0298)==2 and read(0xA8)==credits;pixels(label+' ready capture')
        def reject(scan,label):
            old=list(r.read_bytes(client,0x0287,7));credits=read(0xA8)
            key(scan,8);assert read(0x0298)==2 and list(r.read_bytes(client,0x0287,7))==old and read(0xA8)==credits,label
            pixels(label)
        def accept(scan,raw,label):
            selected=read(0xE0);credits=read(0xA8);start=r.read_word(client,2);visible=None;both=None;first=read(0x90)
            client.call('inject_key',{'key':scan,'action':'press'})
            for _ in range(8):
                tick()
                if read(0x0287+selected)==raw and read(0x0298)==3:
                    if visible is None and r.read_owner(client,read(0x8F))==kexpected():visible=(r.read_word(client,2)-start)&65535
                    if both is None and read(0xE1)==0 and read(0x91)==0:both=(r.read_word(client,2)-start)&65535
            assert visible is not None and both is not None and visible<=6 and both<=12,(label,visible,both)
            timings.append(dict(phase=label,worklist='changed binding footprint and replay',first_back_owner=first,first_visible_vblanks=visible,both_owners_ready_vblanks=both))
            assert read(0x0287+selected)==raw and read(0x0298)==3 and read(0xA6)==8 and read(0xA8)==credits,label
            pixels(label+' consumed while held')
            client.call('inject_key',{'key':scan,'action':'release'})
            for _ in range(4):tick()
            assert read(0x0298)==0;pixels(label+' browse')
        pixels('defaults and first selection')
        timings=[]
        def response(scan,label,selection):
            start=r.read_word(client,2);visible=None;recognized=None;first=read(0x90)
            client.call('inject_key',{'key':scan,'action':'press'})
            end=time.monotonic()+40
            for loops in range(1,25):
                assert time.monotonic()<end,('phase timeout',label)
                tick();now=r.read_word(client,2)
                if read(0xE0)==selection and recognized is None:recognized=(now-start)&65535
                if recognized is not None and visible is None:
                    expected=kexpected();owner=read(0x8F)
                    if r.read_owner(client,owner)==expected:visible=(r.read_word(client,2)-start)&65535
                if loops==2:client.call('inject_key',{'key':scan,'action':'release'})
                if loops>=3 and read(0xE1)==0 and read(0x91)==0:
                    assert recognized is not None and visible is not None,(label,recognized,visible)
                    both=(r.read_word(client,2)-start)&65535
                    assert visible<=6 and both<=12,(label,visible,both)
                    timings.append(dict(phase=label,worklist='old/current keybinding rows and replay',first_back_owner=first,first_visible_vblanks=visible,both_owners_ready_vblanks=both))
                    pixels(label);return
            raise AssertionError(('missing response marker',label))
        for owner in (0,1):
            if read(0x90)!=owner:
                write(0xE1,1<<read(0x90));ready(8)
            assert read(0x90)==owner
            response(0x2C,'keybinding down owner '+str(owner),1)
            response(0x2B,'keybinding up owner '+str(owner),0)
        assert {v['first_back_owner'] for v in timings}=={0,1}
        report['keybinding_response_samples']=timings
        report['response_targets_vblanks']={'first_visible':6,'both_owners_ready':12}

        opening('UP')
        reject(0x2C,'duplicate DOWN rejected')
        reject(1,'duplicate START rejected without starting')
        reject(6,'reserved secondary credit rejected without adding credit')
        for scan in (0x11,0x12):client.call('inject_key',{'key':scan,'action':'press'})
        for _ in range(8):tick()
        assert read(0x0298)==1 and read(0x0287)==27
        client.call('inject_key',{'key':0x11,'action':'release'})
        for _ in range(4):tick()
        assert read(0x0298)==1 and read(0x0287)==27
        for scan in (0x11,0x12):client.call('inject_key',{'key':scan,'action':'release'})
        for _ in range(4):tick()
        check('ambiguous physical keys rejected')
        accept(0x27,58,'UP W and long-to-short erasure')
        opening('UP modifier');accept(0x37,62,'physical SHIFT descriptive name')
        opening('UP punctuation');accept(0x0D,45,'physical MINUS descriptive name')
        opening('UP restore W');accept(0x27,58,'UP W')
        opening('immediate reentry')
        client.call('inject_key',{'key':0x27,'action':'press'})
        for _ in range(8):tick()
        assert read(0x0298)==3
        client.call('inject_key',{'key':0x27,'action':'release'});tick()
        assert read(0x0298)==0
        client.call('inject_key',{'key':select,'action':'press'});tick()
        assert read(0x0298)==1,'first SELECT after capture release was lost'
        client.call('inject_key',{'key':select,'action':'release'})
        for _ in range(4):tick()
        key(0x32,8);assert read(0x0298)==0
        pixels('immediate capture reentry and cancellation')
        opening('same action');accept(0x27,58,'same binding accepted unchanged')
        opening('cancel');key(0x32,8);assert read(0x0298)==0 and read(0x0287)==58;pixels('cancel retains binding')
        # Rebind all remaining consumers through natural capture, including SELECT.
        for i,scan,raw in ((1,0x23,26),(2,0x11,8),(3,0x14,32),(4,0x13,24),(5,0x18,1),(6,0x1A,17)):
            pick(i);opening('action '+str(i))
            if i>=4:reject(0x2B,'fixed menu arrow cannot bind action '+str(i))
            accept(scan,raw,'action '+str(i))
            if i==4:select=0x13
        expected_bindings=[58,26,8,32,24,1,17]
        assert list(r.read_bytes(client,0x0287,7))==expected_bindings
        pick(0)
        client.call('inject_key',{'key':0x2C,'action':'press'})
        for _ in range(20):tick()
        assert read(0xE0)==1
        client.call('inject_key',{'key':0x2C,'action':'release'})
        for _ in range(4):tick()
        for scan in (0x2B,0x2C):client.call('inject_key',{'key':scan,'action':'press'})
        for _ in range(8):tick()
        assert read(0xE0)==1
        for scan in (0x2B,0x2C):client.call('inject_key',{'key':scan,'action':'release'})
        for _ in range(4):tick()
        pick(7);pixels('BACK highlighted')
        key(0x30,8);assert read(0xE0)==7 and read(0x0298)==0
        key(select,6);assert read(0xE0)==0;options_pixels(0)
        key(0x2C,6);key(0x2C,6);key(select,8);pixels('session retained on reopening')
        assert list(r.read_bytes(client,0x0287,7))==expected_bindings
        key(0x32,6)
        for _ in range(3):key(0x2C,6)
        assert read(0xE0)==3;options_pixels(3);key(select,3)
        key(0x2C,3);high_pixels(1);key(select,7)
        row,col=manifest['menus']['credit_back']
        for owner in (0,1):
            frame=r.read_owner(client,owner)
            for i,code in enumerate((11,10,12,20)):
                expected=bytearray(30720);dst=0x2000+row*1280+(col+i)*4;paint(expected,dst,code,10)
                assert r.frame_tile(frame,dst)==r.frame_tile(expected,dst)
        key(select,3);check('rebound SELECT opens and returns every menu with green BACK')
        old=read(0xA8);key(5,3);assert read(0xA8)==old
        key(0x18,3);assert read(0xA8)==old+1;check('rebound credit consumer and original primary disabled')
        key(6,3);assert read(0xA8)==old+2;check('reserved secondary credit remains active outside capture')
        key(1,3);assert read(0xA6)==3 and read(0xA8)==old+2
        client.call('inject_key',{'key':0x1A,'action':'press'})
        wait('rebound start level handoff',lambda:read(0xA6)==2 and read(0xA8)==old+1)
        client.call('inject_key',{'key':0x1A,'action':'release'})
        wait('natural configured live entry',lambda:read(0xA5)==0 and read(0xA0)==0)
        assert (read(0x23),read(0x24))==(3,2)
        movement=[]
        for scan,direction,held in ((0x27,0,1),(0x23,2,2),(0x11,3,4),(0x14,1,8)):
            client.call('inject_key',{'key':scan,'action':'press'})
            for _ in range(8):tick()
            assert read(0x0296)&15==held and read(5)==direction and read(0x0F)==direction,(scan,read(0x0296),read(5),read(0x0F))
            movement.append({'scan':scan,'held_action_mask':held,'requested_direction':direction})
            client.call('inject_key',{'key':scan,'action':'release'})
            for _ in range(4):tick()
        report['movement']=movement;check('all four rebound gameplay movement consumers')
        for scan in (0x27,0x23):client.call('inject_key',{'key':scan,'action':'press'})
        for _ in range(8):tick()
        assert read(5)==255
        for scan in (0x27,0x23):client.call('inject_key',{'key':scan,'action':'release'})
        for _ in range(4):tick()
        for scan in (0x27,0x14):client.call('inject_key',{'key':scan,'action':'press'})
        for _ in range(8):tick()
        assert read(5)==1
        for scan in (0x27,0x14):client.call('inject_key',{'key':scan,'action':'release'})
        check('movement opposition and horizontal priority preserved')
        client.close();monitor.stop(process)
        process,client=r.launch_fast(monitor,ROOT/'docs/reference/xroar/src/xroar',BUILD/'ladybug.rom')
        ids=monitor.setup(client,[0x1900]);tick()
        assert list(r.read_bytes(client,0x0287,7))==defaults and (read(0xEA),read(0xEB))==(3,1)
        write(0xEA,12);write(0xEB,99)
        monitor.clear(client,ids);ps=r.symbols(BUILD/'ladybug-presentation-runtime.map')
        ids=monitor.setup(client,[ps['demo_tick']]);assert client.run_to_breakpoint(40)['pc']==ps['demo_tick']
        assert read(0xA5)==4 and (read(0x23),read(0x24))==(3,1)
        check('cold reset defaults and natural demo retains its own gameplay defaults')
        report['status']='pass'
