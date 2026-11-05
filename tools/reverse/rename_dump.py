"""Rename FUN_<addr> symbols in a Ghidra decompile dump using the DLL export table.

Exports of 8BitDoAdvance.dll point at jmp stubs (incremental linking), so both the stub
address and its target get the export name.
"""
import struct, re, sys
if len(sys.argv) != 5:
    sys.exit('usage: rename_dump.py 8BitDoAdvance.dll exports.txt ghidra_dump.c out.c')
dll=sys.argv[1]
d=open(dll,'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]; nsec=struct.unpack_from('<H',d,pe+6)[0]; optsz=struct.unpack_from('<H',d,pe+20)[0]
opt=pe+24; imagebase=struct.unpack_from('<I',d,opt+28)[0]
secs=[]; s=opt+optsz
for i in range(nsec):
    vsz,va,rsz,roff=struct.unpack_from('<IIII',d,s+i*40+8); secs.append((va,vsz,roff,rsz))
def va2off(va):
    rva=va-imagebase
    for sva,vsz,roff,rsz in secs:
        if sva<=rva<sva+max(vsz,rsz): return roff+(rva-sva)
    return None
names={}
for line in open(sys.argv[2]):
    if not line.startswith('0x'): continue
    a,n=line.split(); a=int(a,16)
    clean=re.sub(r'^_','',n); clean=re.sub(r'@\d+$','',clean)
    names[a]=clean
mapping={}  # FUN_addr -> name
thunks=0
for a,n in names.items():
    off=va2off(a)
    if off is None: continue
    if d[off]==0xE9:
        rel=struct.unpack_from('<i',d,off+1)[0]; tgt=a+5+rel; thunks+=1
        mapping[f'FUN_{tgt:08x}']=n
    mapping[f'FUN_{a:08x}']=n
print(f"exports={len(names)} via_jmp={thunks} mapping={len(mapping)}", file=sys.stderr)
src=open(sys.argv[3]).read()
pat=re.compile(r'FUN_[0-9a-f]{8}')
src=pat.sub(lambda m: mapping.get(m.group(0), m.group(0)), src)
# also header lines "// ==== FUN_x @ addr" now renamed; write out
open(sys.argv[4],'w').write(src)
found=sum(1 for n in mapping.values() if re.search(r'^// =+ '+re.escape(n)+r' @', src, re.M))
print(f"functions present in dump after rename: {found}", file=sys.stderr)
