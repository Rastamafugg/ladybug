local frame = 0
local finished = false
local space = nil
local ioports = nil
local video = nil
local out = assert(io.open("/tmp/rsch014-A10-rate-window.tsv", "w"))
local vout = assert(io.open("/tmp/rsch014-A10-rate-window-video.bin", "wb"))
local bout = assert(io.open("/tmp/rsch014-A10-rate-window-background.bin", "wb"))
local rout = assert(io.open("/tmp/rsch014-A10-rate-window-work-ram.bin", "wb"))

local actions = {
  {300, ":COIN", 0x01, 0x01, "coin1", true},
  {303, ":COIN", 0x01, 0x00, "coin1", false},
  {360, ":IN0", 0x20, 0x01, "start1", true},
  {365, ":IN0", 0x20, 0x00, "start1", false},
  {620, ":CONTP1", 0x02, 0x01, "down", true},
  {690, ":CONTP1", 0x02, 0x00, "down", false},
  {690, ":CONTP1", 0x04, 0x01, "right", true},
  {710, ":CONTP1", 0x04, 0x00, "right", false},
  {710, ":CONTP1", 0x08, 0x01, "up", true},
  {840, ":CONTP1", 0x08, 0x00, "up", false},
}

local function find_field(tag, mask)
    local port = assert(ioports[tag], "missing input port " .. tag)
    for name, field in pairs(port.fields) do
        if field.mask == mask then return field, name end
    end
    error(string.format("missing field %s mask %02x", tag, mask))
end

local function initialize()
    local machine = manager:machine()
    space = machine.devices[":maincpu"].spaces["program"]
    local fixture = io.open("/tmp/ladybug-maincpu.bin", "rb")
    if not fixture then
        out:write("ROM_GUARD\tFAIL\tfixture_missing\n")
        out:flush(); out:close(); vout:close(); bout:close(); rout:close()
        finished = true
        return
    end
    local expected = fixture:read("*a")
    fixture:close()
    if #expected ~= 0x6000 then
        out:write(string.format("ROM_GUARD\tFAIL\tfixture_length\t%d\n", #expected))
        out:flush(); out:close(); vout:close(); bout:close(); rout:close()
        finished = true
        return
    end
    for address = 0, 0x5fff do
        local expected_byte = expected:byte(address + 1)
        local live_byte = space:read_u8(address)
        if live_byte ~= expected_byte then
            out:write(string.format("ROM_GUARD\tFAIL\tbyte_mismatch\t%04x\t%02x\t%02x\n",
                address, live_byte, expected_byte))
            out:flush(); out:close(); vout:close(); bout:close(); rout:close()
            finished = true
            return
        end
    end
    out:write("ROM_GUARD\tPASS\tbytes=24576\tsha256=3ca5f2a3fe65c982d55da6f873036119cdfd4da81bc1304a02393622a4cd7c12\n")
    ioports = machine:ioport().ports
    video = machine:video()
    for _, action in ipairs(actions) do
        action.field, action.field_name = find_field(action[2], action[3])
    end
    local width, height = video:size()
    out:write(string.format("M\t%d\t%d\n", width, height))
end

local function apply_actions()
    for _, action in ipairs(actions) do
        if action[1] == frame then
            action.field:set_value(action[4])
            out:write(string.format("I\t%d\t%s\t%s\t%s\n",
                frame, action[5], tostring(action[6]), action.field_name))
        end
    end
end

local function span_hex(address, length)
    local bytes = {}
    for offset = 0, length - 1 do
        bytes[#bytes + 1] = string.format("%02x", space:read_u8(address + offset))
    end
    return table.concat(bytes)
end

local function dump_frame()
    if frame >= 1513 then vout:write(video:pixels()) end
    local bytes = {}
    for address = 0xd000, 0xd7ff do
        bytes[#bytes + 1] = string.char(space:read_u8(address))
    end
    bout:write(table.concat(bytes))
    bytes = {}
    for address = 0x6000, 0x6fff do
        bytes[#bytes + 1] = string.char(space:read_u8(address))
    end
    rout:write(table.concat(bytes))
end

emu.register_frame_done(function()
    if finished then return end
    if frame == 0 then initialize() end
    if finished then return end
    frame = frame + 1
    apply_actions()
    if frame >= 1513 then
        dump_frame()
        if frame == 1513 then
            local dsw0 = space:read_u8(0x9002)
            local easy_medium = math.floor(dsw0 / 2) % 2 == 1
            local pre = table.concat({
                span_hex(0x9002, 1), span_hex(0x6065, 1), span_hex(0x606e, 2), span_hex(0x61e1, 1),
                span_hex(0x61b5, 1), span_hex(0x61b6, 1), span_hex(0x61b7, 1),
                span_hex(0x61c3, 1), span_hex(0x605a, 1), span_hex(0x601c, 50)
            }, "\t")
            local preconditions =
                easy_medium and space:read_u8(0x6065) == 0 and space:read_u8(0x606e) == 1 and
                space:read_u8(0x606f) == 0 and space:read_u8(0x61e1) == 0 and
                space:read_u8(0x61b5) == 0 and space:read_u8(0x61b6) == 0x10 and
                space:read_u8(0x61b7) == 0x0d and space:read_u8(0x61c3) == 0x10 and
                space:read_u8(0x605a) == 0x38 and
                span_hex(0x601c, 50) == "81080f00100040ae001082685600001267961801815886180100000000000000000000000000000000000000000000000000"
            out:write("P\t1513\t" .. pre .. "\n")
            if not preconditions then
                out:write("ABORT\t1513\tprecondition_mismatch\n")
                out:flush(); out:close(); vout:close(); bout:close(); rout:close()
                finished = true
                return
            end
            space:write_u8(0x606E, 0x07)
            local readback = space:read_u8(0x606e)
            out:write(string.format("W\t1513\t606E\t07\t%02x\n", readback))
            if readback ~= 0x07 then
                out:write("ABORT\t1513\twrite_readback_mismatch\n")
                out:flush(); out:close(); vout:close(); bout:close(); rout:close()
                finished = true
                return
            end
        else
            out:write("S\t" .. frame .. "\t" .. table.concat({
                span_hex(0x6065, 1), span_hex(0x606e, 2), span_hex(0x61e1, 1),
                span_hex(0x61b5, 1), span_hex(0x61b6, 1), span_hex(0x61b7, 1),
                span_hex(0x61c3, 1), span_hex(0x605a, 1), span_hex(0x602b, 5),
                span_hex(0x6030, 5), span_hex(0x601c, 15)
            }, "\t") .. "\n")
        end
    end
    out:flush()
    if frame >= 1519 then
        out:close(); vout:close(); bout:close(); rout:close(); finished = true
    end
end)
