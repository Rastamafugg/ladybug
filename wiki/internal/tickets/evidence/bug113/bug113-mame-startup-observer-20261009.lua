local exports = {name="bootprobe", version="1.0", description="Read-only boot observer"}
function exports.startplugin()
  local root = "/mnt/e/projects/ladybug/build/bug113/mame-diagnosis/"
  local frame = 0
  local log
  local function dump(space, name, first, last)
    local f = assert(io.open(root .. name, "wb"))
    local bytes = {}
    for a = first, last do bytes[#bytes+1] = string.char(space:read_u8(a)) end
    f:write(table.concat(bytes)); f:close()
  end
  emu.register_start(function()
    log = assert(io.open(root .. "probe2-frames.tsv", "w"))
    log:write("frame\tpc\ts\tx\ty\tu\tcc\tboot_flag\tboot_proof\tpars\tmode\tcell\thold\towner\tfront\tback\tpending\tirq_frames\n")
  end)
  emu.register_frame_done(function()
    frame = frame + 1
    local cpu = manager:machine().devices[":maincpu"]
    local space = cpu.spaces["program"]
    local regs = cpu.state
    local pars = {}
    for a=0xffa0,0xffa7 do pars[#pars+1] = string.format("%02x",space:read_u8(a)) end
    log:write(string.format("%d\t%04x\t%04x\t%04x\t%04x\t%04x\t%02x\t%02x\t%02x\t%s\t%02x\t%04x\t%02x\t%02x\t%02x\t%02x\t%02x\t%04x\n", frame,
      regs.PC.value,regs.S.value,regs.X.value,regs.Y.value,regs.U.value,regs.CC.value,
      space:read_u8(0x2f0),space:read_u8(0x2f1),table.concat(pars," "),
      space:read_u8(0xa5),space:read_u16(0xac),space:read_u8(0xd4),space:read_u8(0xd9),
      space:read_u8(0x8f),space:read_u8(0x90),space:read_u8(0x91),space:read_u16(2)))
    log:flush()
    if frame == 26 or frame == 135 or frame == 240 or frame == 360 or frame == 480 then
      dump(space, "probe2-memory-" .. frame .. ".bin",0,0xffff)
    end
  end)
  emu.register_stop(function() if log then log:close() end end)
end
return exports
