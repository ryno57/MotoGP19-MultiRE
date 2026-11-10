import sys
from io import BytesIO
from minidump.minidumpfile import MinidumpFile
from minidump.streams.ContextStream import CONTEXT

path = sys.argv[1]
data = open(path, 'rb').read()
mf = MinidumpFile.parse(path)

mods = []
for m in mf.modules.modules:
    name = m.name.split('\\')[-1] if m.name else '?'
    mods.append((m.baseaddress, m.baseaddress + m.size, name))

def mod_for(addr):
    for base, end, name in mods:
        if base <= addr < end:
            return name, addr - base
    return None, None

reader = mf.get_reader()

def read_mem(addr, size):
    try:
        return reader.read(addr, size)
    except Exception:
        return None

print('threads:', len(mf.threads.threads))
for t in mf.threads.threads:
    rva = t.ThreadContext.Rva
    size = t.ThreadContext.DataSize
    if rva == 0 or size == 0:
        continue
    try:
        ctx = CONTEXT.parse(BytesIO(data[rva:rva + size]))
    except Exception:
        continue

    # scan 16 KiB of stack above RSP
    stack_size = min(t.Stack.MemoryLocation.DataSize, 0x4000)
    raw = read_mem(ctx.Rsp, stack_size)
    if raw is None:
        print(f'tid={t.ThreadId} RSP={ctx.Rsp:016x} stack illisible')
        continue

    hits = []
    for off in range(0, len(raw) - 8 + 1, 8):
        val = int.from_bytes(raw[off:off + 8], 'little')
        name, moff = mod_for(val)
        if name and any(k in name.lower() for k in ('motogp19', 'ue4ss', 'dbghelp')):
            hits.append((ctx.Rsp + off, name, moff))

    if hits:
        print(f'--- tid={t.ThreadId} rip={ctx.Rip:016x} rsp={ctx.Rsp:016x} hits={len(hits)}')
        for addr, name, moff in hits[:40]:
            print(f'  [{addr:016x}] {name}+0x{moff:x}')
