"""Assemble isolated adaptive bookkeeping; no delivered source/ROM modifications."""
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path

def symbols(path):
    return {k:int(v,16) for k,v in re.findall(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",path.read_text(),re.M)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("root",type=Path)
    ap.add_argument("reference",type=Path)
    ap.add_argument("output",type=Path)
    ap.add_argument("--reference-revision",default="cba520588abf4a8ab32314ec61a16d58b40b7186")
    a=ap.parse_args();root=a.root;out=root/"build/adaptive-fit";out.mkdir(parents=True,exist_ok=True)
    source=root/"src/adaptive_runtime.s";s=source.read_text()
    def label(name):return re.search(r"^"+name+r"$",s,re.M).start()
    prefix=s[:s.index("        org $BD44")]
    clock=s[label("adaptive_clock"):s.index("; Already displayed barrier")]
    append=s[label("adaptive_append"):s.index("; A=target owner")]
    complete=s[label("adaptive_complete"):label("adaptive_end")]
    def assemble(name,path):
        subprocess.run(["lwasm","--6809","--format=raw","--output="+str(out/(name+".bin")),"--list="+str(out/(name+".lst")),"--map="+str(out/(name+".map")),str(path)],check=True)
        return (out/(name+".bin")).read_bytes()
    all_bytes=assemble("helper",source)
    (out/"mapped.s").write_text(prefix+"adaptive_start equ $BD44\n        org $09FD\n"+clock+append+complete+"mapped_end\n")
    mapped=assemble("mapped",out/"mapped.s");ms=symbols(out/"mapped.map")
    body=s[s.index("        org $BD44"):]
    for name,end in [("adaptive_clock","; Already displayed barrier"),("adaptive_append","; A=target owner"),("adaptive_complete","adaptive_end\n")]:
        begin=re.search(r"^"+name+r"$",body,re.M).start();last=body.index(end)
        body=body[:begin]+body[last:]
    for name in ["adaptive_reset","adaptive_append","adaptive_complete"]:body=body.replace("lbra "+name,"jmp "+name)
    body=body.replace("lbsr adaptive_clock","jsr adaptive_clock").replace("lbsr adaptive_append","jsr adaptive_append")
    extern="".join(f"{name} equ ${ms[name]:04X}\n" for name in ["adaptive_clock","adaptive_reset","adaptive_append","adaptive_complete"])
    (out/"banked.s").write_text(prefix+extern+body)
    banked=assemble("banked",out/"banked.s")
    callback="""        org $1800
        jmp tick
        rts
        nop
        nop
        rts
        nop
        nop
        rts
        nop
        nop
        org $1810
tick
        lda #$20
        sta $007F
        ldd $BD26
        std $0009
        clra
        rts
callback_end
"""
    (out/"callbacks.s").write_text(callback)
    assemble("callbacks",out/"callbacks.s")
    b=a.reference/"build";layout=json.loads((b/"ladybug-sparse-layout.json").read_text())
    sys.path.insert(0,str(a.reference/"scripts"))
    from gmc_lzss import compress,decompress
    raw=(b/"ladybug-player-sparse.bin").read_bytes()+(b/"ladybug-gate-transitions.bin").read_bytes()+(b/"ladybug-presentation-sparse.bin").read_bytes()
    prior=next(x for x in layout["compression"]["streams"] if x["name"]=="page39")
    encoded=compress(raw+banked);assert decompress(encoded,len(raw)+len(banked))==raw+banked
    source_free=layout["gmc"]["spare_bytes"]
    result={"kind":"assembled bookkeeping fit with unbound production callbacks", "date":"2026-09-28",
      "base_commit":a.reference_revision,
      "worktree":str(root),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
      "reference_rom_sha256":hashlib.sha256((b/"ladybug.rom").read_bytes()).hexdigest(),
      "monolithic_bytes":len(all_bytes),"monolithic_limit":698,"monolithic_over":len(all_bytes)-698,
      "banked_bytes":len(banked),"banked_limit":698,"banked_free":698-len(banked),
      "mapped_bytes":len(mapped),"reclaimed_project_queue_bytes":220,"mapped_free":220-len(mapped),
      "copy_table_after_one_raw_segment":layout["gmc"]["sparse_copy_table_bytes"]+8,
      "cartridge_source_free_before":source_free,"raw_delivery_margin":source_free-len(banked),
      "page39_transport":{"old_raw_bytes":len(raw),"old_compressed_bytes":prior["compressed_bytes"],
          "new_raw_bytes":len(raw)+len(banked),"new_compressed_bytes":len(encoded),
          "delta":len(encoded)-prior["compressed_bytes"],"remaining_source_margin":source_free-(len(encoded)-prior["compressed_bytes"]),"roundtrip_exact":True},
      "verdict":("PASS: split bookkeeping arithmetic fits; callbacks remain unbound, no ROM installation" if len(banked)<=698 and len(mapped)<=220 and source_free>=len(banked) else "REJECTED: component or cartridge arithmetic fails; no ROM installation"),
      "unresolved":["real logic/input/renderer/audio callback bridges", "loader copy ordering and complete fragmented source packing", "transient pixel restoration and natural two-owner playback", "complete 27000/54000 worklist timing"],
      "limits":["Mapped allocation replaces old projector/queue; those functions cannot coexist with the prototype.","Callback stubs implement synthetic counting only, not gameplay, pixels or audio.","No new compression stream/page, hard limit or delivered ROM is installed.","Measured source arithmetic excludes further integration code and loader bytes; complete packing is a separate gate."]}
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
