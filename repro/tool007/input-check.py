from pathlib import Path
import sys,json,tempfile,shutil,importlib.util
from unittest.mock import patch
root=Path('.').resolve();spec=importlib.util.spec_from_file_location('adaptive_builder',root/'scripts/build_adaptive_runtime.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
commands=[]
class Captured(Exception):pass
for flag in (0,1):
 with tempfile.TemporaryDirectory() as temp:
  dest=Path(temp)
  for name in ('ladybug.map','ladybug-audio-runtime.map','ladybug-audio-runtime.bin','ladybug_audio_symbols.inc'):shutil.copy(root/'build'/name,dest/name)
  def run(command,**kwargs):
   if command[0]=='lwasm' and str(root/'src/main.s') in command:
    assert f'-DINPUT_JOYSTICK={flag}' in command
    commands.append({'selected_joystick':flag,'emitted_define':f'-DINPUT_JOYSTICK={flag}'});raise Captured()
  with patch.object(sys,'argv',['builder','--phase','link','--root',str(root),'--build-dir',str(dest),'--input-joystick',str(flag)]),patch.object(builder.subprocess,'run',run):
   try:builder.main()
   except Captured:pass
   else:raise AssertionError('main command not reached')
assert '--input-joystick "$INPUT_JOYSTICK"' in (root/'scripts/build.sh').read_text()
(root/'repro/tool007/input-propagation-20261001.json').write_text(json.dumps({'builder_command_controls':commands,'build_script_forwards_selected_flag':True},indent=2)+'\n');print(commands)
