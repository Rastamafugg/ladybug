"""Future Phase B assertions. Never launches or imports production runtime."""
import argparse,json
from pathlib import Path
DENIED_APIS=('subprocess','socket','signal','select','ctypes','os.kill','os.exec','xroar','gdb')
def assert_sprite_contract(mod):
 assert mod.decode_sprite(bytes((255,0,0)),0)==[]
 try:mod.decode_sprite(bytes((255,0,1)),0)
 except ValueError:pass
 else:raise AssertionError('escape truncation accepted')
def assert_compare_contract(mod):
 assert mod.compare_bytes(b'ab',b'ab')['passed'] and not mod.compare_bytes(b'ab',b'ac')['passed']
def assert_checkpoint_contract(mod):
 b=mod.Budget(1);b.tick()
 try:b.tick()
 except TimeoutError:pass
 else:raise AssertionError('checkpoint overflow accepted')
CASES=(assert_sprite_contract,assert_compare_contract,assert_checkpoint_contract)
def main():
 p=argparse.ArgumentParser();p.add_argument('--approval',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();x=json.loads(a.approval.read_text())
 if x.get('execution_approved') is not True:raise SystemExit('offline checks require separate explicit approval')
 raise SystemExit('offline harness not enabled; output must be unused and scoped')
if __name__=='__main__':main()
