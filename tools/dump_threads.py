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

rows = []
for t in mf.threads.threads:
    rva = t.ThreadContext.Rva
    size = t.ThreadContext.DataSize
    if rva == 0 or size == 0:
        continue
    try:
        ctx = CONTEXT.parse(BytesIO(data[rva:rva + size]))
    except Exception as e:
        continue
    name, off = mod_for(ctx.Rip)
    rows.append((t.ThreadId, ctx.Rip, ctx.Rsp, ctx.Rbp, name, off))

print('threads total:', len(rows))
print('--- threads dans motogp19 / UE4SS / dbghelp / KERNELBASE ---')
for tid, rip, rsp, rbp, name, off in rows:
    if name and any(k in name.lower() for k in ('motogp19', 'ue4ss', 'dbghelp', 'kernelbase')):
        print(f'tid={tid:<6} rip={rip:016x} rsp={rsp:016x} rbp={rbp:016x}  {name}+0x{off:x}')

print('--- tous les threads (rip module+off) ---')
for tid, rip, rsp, rbp, name, off in rows:
    if name:
        print(f'tid={tid:<6} {name}+0x{off:x}  rsp={rsp:016x} rbp={rbp:016x}')
    else:
        print(f'tid={tid:<6} ?? {rip:016x}  rsp={rsp:016x} rbp={rbp:016x}')
