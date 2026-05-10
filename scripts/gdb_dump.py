#!/usr/bin/env python3
"""Talk to xroar's GDB stub on 127.0.0.1:65520, set BP at post_blit, dump state.
Pure GDB-remote-protocol over socket — does not require a 6809-aware GDB binary."""
import socket, sys, time

HOST, PORT = "127.0.0.1", 65520
POST_BLIT = "c097"   # update to match build/ladybug.lst

def chk(s):
    return f"{sum(s.encode()) & 0xff:02x}"

def pkt(s):
    return f"${s}#{chk(s)}".encode()

def recv_raw(sk, timeout=2.0):
    sk.settimeout(timeout)
    out = b""
    try:
        while True:
            c = sk.recv(4096)
            if not c:
                break
            out += c
            # stop reading when we have at least one complete $...#XX
            if b"$" in out and b"#" in out:
                i = out.index(b"$")
                j = out.index(b"#", i)
                if len(out) >= j + 3:
                    return out
    except socket.timeout:
        return out

def parse_pkt(raw):
    """Strip leading +/- and return packet body (text between $ and #)."""
    if not raw:
        return None
    if b"$" not in raw or b"#" not in raw:
        return raw  # ack only
    i = raw.index(b"$")
    j = raw.index(b"#", i)
    return raw[i+1:j].decode(errors="replace")

def cmd(sk, c, timeout=4.0):
    sk.sendall(pkt(c))
    raw = recv_raw(sk, timeout=timeout)
    sk.sendall(b"+")
    return parse_pkt(raw), raw

def main():
    sk = socket.create_connection((HOST, PORT))
    sk.sendall(b"+")  # initial ack to clear any pending nack

    print(f"=== ? (stop reason) ===\n  {cmd(sk, '?')[0]!r}")
    print(f"=== qSupported ===\n  {cmd(sk, 'qSupported')[0]!r}")
    print(f"=== Z0,{POST_BLIT},1 ===\n  {cmd(sk, f'Z0,{POST_BLIT},1')[0]!r}")
    print("=== c (continue, expect halt at BP) ===")
    body, raw = cmd(sk, "c", timeout=10.0)
    print(f"  body={body!r}  raw={raw!r}")

    queries = [
        ("g (regs: CC A B DP X Y U S PC = 14 bytes hex)", "g"),
        ("DP counter $0205 (1 B)",   "m0205,1"),
        ("FB $2000..$201F (32 B)",   "m2000,20"),
        ("FB $20A0..$20BF",          "m20a0,20"),
        ("FB $2200..$221F",          "m2200,20"),
        ("FB $4000..$401F",          "m4000,20"),
        ("FB $8000..$801F",          "m8000,20"),
        ("PAR exec   $FFA0..$FFA7",  "mffa0,8"),
        ("PAR task   $FFA8..$FFAF",  "mffa8,8"),
        ("par_table  $C0DA..$C0E1 (RAM)",  "mc0da,8"),
        ("counter $0005",            "m0005,1"),
        ("counter $0205",            "m0205,1"),
        ("GIME $FF98..$FF9F",        "mff98,8"),
        ("blit code $C0BA..$C0CE",   "mc0ba,14"),
        ("palette $FFB0..$FFBF",     "mffb0,10"),
    ]
    for label, c in queries:
        body, _ = cmd(sk, c)
        print(f"=== {label} ===\n  {body!r}")
    sk.close()

if __name__ == "__main__":
    main()
