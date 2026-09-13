"""Separately approved local-only Phase B runner; never imports supervisor."""
import argparse,builtins,hashlib,json,os
from pathlib import Path
DENIED_MODULES={'subprocess','socket','signal','select','ctypes','serial','xroar','gdb'}
_real_import=builtins.__import__
def _deny_import(name,*a,**k):
 if name.split('.')[0] in DENIED_MODULES|{'supervisor','name_sequence_probe','gmc_boot_probe'}:raise RuntimeError('denied offline import '+name)
 return _real_import(name,*a,**k)
def install_denial_guards():builtins.__import__=_deny_import
def assert_sprite_contract(m):
 assert list(m.sprite_operations(bytes((255,0,0)),0,m.Budget(100)))==[]
 assert list(m.sprite_operations(bytes((0,1,0,255,0,0)),0,m.Budget(100)))[0]==(1,0,1)
 try:list(m.sprite_operations(bytes((255,0,1)),0,m.Budget(100)))
 except Exception:pass
 else:raise AssertionError('truncated escape accepted')
def assert_compare_contract(m):
 assert m.compare_bytes(b'ab',b'ab',m.Budget(100))['passed'];r=m.compare_bytes(b'ab',b'ac',m.Budget(100));assert r['mismatches']==1 and r['samples'][0]['offset']==1
def assert_checkpoint_contract(m):
 b=m.Budget(1.0,lambda:2.0)
 try:b.check()
 except TimeoutError:pass
 else:raise AssertionError('deadline expiry accepted')
CASES=(assert_sprite_contract,assert_compare_contract,assert_checkpoint_contract)
def run_cases(approval_path,output_path,comparator_path,expected_hash):
 a=json.loads(Path(approval_path).read_text())
 if a.get('offline_approved') is not True or a.get('execution_approved') is True:raise PermissionError('separate offline approval required; runtime approval forbidden')
 out=Path(output_path).resolve();root=Path.cwd().resolve()/'repro/rsch009/offline-checks'
 if root not in out.parents or out.exists():raise ValueError('output must be new and scoped')
 if hashlib.sha256(Path(comparator_path).read_bytes()).hexdigest()!=expected_hash:raise ValueError('comparator hash mismatch')
 install_denial_guards();import importlib.util
 s=importlib.util.spec_from_file_location('local_comparator',comparator_path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 results=[]
 for c in CASES:c(m);results.append({'case':c.__name__,'passed':True})
 out.mkdir(parents=True);(out/'results.json').write_text(json.dumps({'status':'pass','cases':results})+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--approval',required=True);p.add_argument('--output',required=True);p.add_argument('--comparator',required=True);p.add_argument('--hash',required=True);a=p.parse_args();run_cases(a.approval,a.output,a.comparator,a.hash)
if __name__=='__main__':main()
