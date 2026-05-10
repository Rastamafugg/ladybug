#!/usr/bin/env python3
"""Standalone probe: connect, halt at post_blit, then dump arbitrary memory ranges
passed as args. Each arg is a GDB-remote 'm<addr>,<len>' query (no leading $)."""
import socket, sys

HOST, PORT = "127.0.0.1", 65520
POST_BLIT = "c097"

def chk(s): return f"{sum(s.encode()) & 0xff:02x}"
def pkt(s): return f"${s}#{chk(s)}".encode()

def cmd(sk, c, timeout=5.0):
    sk.sendall(pkt(c))
    sk.settimeout(timeout)
    out = b""
    while True:
        try: data = sk.recv(4096)
        except socket.timeout: break
        if not data: break
        out += data
        if b"$" in out and b"#" in out:
            i = out.index(b"$"); j = out.index(b"#", i)
            if len(out) >= j + 3:
                sk.sendall(b"+")
                return out[i+1:j].decode(errors="replace")
    return None

sk = socket.create_connection((HOST, PORT))
sk.sendall(b"+")
print(f"?       -> {cmd(sk, '?')!r}")
print(f"Z0      -> {cmd(sk, f'Z0,{POST_BLIT},1')!r}")
print(f"c       -> {cmd(sk, 'c', timeout=8.0)!r}")
for q in sys.argv[1:]:
    print(f"{q:18s} -> {cmd(sk, q)!r}")
sk.close()
