#!/usr/bin/env python3
"""Extract embedded files from a .NET single-file bundle (apphost)."""
import struct, sys, os, zlib
MARKER = bytes.fromhex("8b1202b96a612038727b930214d7a03213f5b9e6efae3318ee3b2dce24b36aae")
def read_str(d, off):
    # 7-bit encoded length prefix
    n=0; shift=0
    while True:
        b=d[off]; off+=1
        n |= (b&0x7f)<<shift
        if not b&0x80: break
        shift+=7
    return d[off:off+n].decode('utf-8'), off+n
src, outdir = sys.argv[1], sys.argv[2]
d=open(src,'rb').read()
mi=d.find(MARKER)
assert mi>0, "no bundle marker"
hdr_off=struct.unpack_from('<q', d, mi-8)[0]
p=hdr_off
major,minor,nfiles=struct.unpack_from('<IIi', d, p); p+=12
bundle_id,p=read_str(d,p)
print(f"bundle v{major}.{minor} files={nfiles} id={bundle_id}")
if major>=2:
    deps_off,deps_sz,rc_off,rc_sz,flags=struct.unpack_from('<qqqqQ', d, p); p+=40
    print(f"deps.json @{deps_off}+{deps_sz} runtimeconfig @{rc_off}+{rc_sz} flags={flags:#x}")
TYPES={0:'Unknown',1:'Assembly',2:'NativeBinary',3:'DepsJson',4:'RuntimeConfigJson',5:'Symbols'}
os.makedirs(outdir, exist_ok=True)
for i in range(nfiles):
    off,size=struct.unpack_from('<qq', d, p); p+=16
    csize=0
    if major>=6:
        csize=struct.unpack_from('<q', d, p)[0]; p+=8
    ftype=d[p]; p+=1
    rel,p=read_str(d,p)
    if csize:
        blob=zlib.decompress(d[off:off+csize], -15)
    else:
        blob=d[off:off+size]
    dst=os.path.join(outdir, rel.replace('\\','/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst,'wb').write(blob)
    print(f"{TYPES.get(ftype,ftype):18s} {size:>10} {'(compressed %d)'%csize if csize else '':20s} {rel}")
