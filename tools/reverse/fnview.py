#!/usr/bin/env python3
"""Print selected functions from a Ghidra decompile dump, minus debug-build boilerplate."""
import re, sys
path = sys.argv[1]
names = sys.argv[2:]
src = open(path).read()
parts = re.split(r'^// =+ (\S+) @ ([0-9a-f]+) depth=\d+ =+\n', src, flags=re.M)
funcs = {}
for i in range(1, len(parts), 3):
    funcs.setdefault(parts[i], parts[i+2])
def clean(body):
    out = []; skip = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith('/* WARNING') or 'CheckForDebuggerJustMyCode' in s or '0xcccccccc' in s or '-0x33333334' in s or s.startswith('uStack_8 = DAT_') or s.startswith('_RTC_CheckStackVars'): continue
        if re.match(r'^(puVar|piVar)\d+ = (a|&)', s): continue
        if re.match(r'^for \(iVar\d+ = 0x[0-9a-f]+; iVar\d+ != 0; iVar\d+ = iVar\d+ \+ -1\) \{$', s): skip = True; continue
        if skip:
            if s == '}': skip = False
            continue
        if re.match(r'^(undefined|int|uint|char|byte|short|ushort|bool|ulonglong|longlong)\d* \*?[a-zA-Z_0-9\[\]]+;$', s): continue
        if s == '': continue
        out.append(line)
    return '\n'.join(out)
if names == ['--list']:
    print(' '.join(funcs)); sys.exit()
for n in names:
    matches = [k for k in funcs if k == n] or [k for k in funcs if re.fullmatch(n, k)]
    if not matches:
        print(f"////////// {n}: NOT FOUND"); continue
    for k in matches:
        print(f"////////// {k}"); print(clean(funcs[k]))
