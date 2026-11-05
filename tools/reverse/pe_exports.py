#!/usr/bin/env python3
"""Parse a PE export table: prints "0xADDR name" per export (stdcall decoration kept)."""
import struct, sys
d=open(sys.argv[1],'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]
nsec=struct.unpack_from('<H',d,pe+6)[0]; optsz=struct.unpack_from('<H',d,pe+20)[0]
opt=pe+24; magic=struct.unpack_from('<H',d,opt)[0]; is64=magic==0x20b
imagebase=struct.unpack_from('<Q' if is64 else '<I', d, opt+(24 if is64 else 28))[0]
secs=[]
s=opt+optsz
for i in range(nsec):
    name=d[s+i*40:s+i*40+8].rstrip(b'\0').decode()
    vsz,va,rsz,roff=struct.unpack_from('<IIII',d,s+i*40+8); secs.append((name,va,vsz,roff,rsz))
def rva2off(rva):
    for n,va,vsz,roff,rsz in secs:
        if va<=rva<va+max(vsz,rsz): return roff+(rva-va)
    raise ValueError(hex(rva))
exp_rva,exp_sz=struct.unpack_from('<II',d,opt+(112 if is64 else 96))
e=rva2off(exp_rva)
_,_,_,name_rva,base,nfunc,nnames,addr_funcs,addr_names,addr_ords=struct.unpack_from('<IIIIIIIIII',d,e)
funcs=[struct.unpack_from('<I',d,rva2off(addr_funcs)+4*i)[0] for i in range(nfunc)]
names=[struct.unpack_from('<I',d,rva2off(addr_names)+4*i)[0] for i in range(nnames)]
ords=[struct.unpack_from('<H',d,rva2off(addr_ords)+2*i)[0] for i in range(nnames)]
print(f"imagebase={imagebase:#x} exports={nfunc} named={nnames}")
out=[]
for nr,o in zip(names,ords):
    off=rva2off(nr); nm=d[off:d.index(b'\0',off)].decode()
    out.append((funcs[o],nm))
for rva,nm in sorted(out): print(f"{imagebase+rva:#010x} {nm}")
