"""Reproducible offline audit across EA 1.0, Steam 1.0 and Steam 1.01.

Builds and exports the actual C# stubs once per profile, then runs the same
execution/ABI/continuation suites against each. Does not open a game process.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/audit'

def run(args,env=None,quiet=False):
    env=(env or os.environ).copy()
    env['DOTNET_CLI_UI_LANGUAGE']='en'
    env['PYTHONIOENCODING']='utf-8'
    result=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf8',errors='replace')
    output=result.stdout+result.stderr
    if result.returncode or not quiet:print(output.rstrip(),flush=True)
    if result.returncode:raise RuntimeError(f'Failed ({result.returncode}): {args}')
    return output

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    run(['dotnet','build','RA3MT.slnx','-c','Release','--nologo'])
    run([sys.executable,'tools/analysis/audit_uprising.py'])
    selfcheck=['dotnet','run','--project','src/RA3MT.SelfCheck','-c','Release','--no-build','--']
    run(selfcheck+['uprisingtest'])
    scripts=['test_disabled_stubs.py','test_execution_stubs.py','test_rank_dispatcher.py',
             'test_bridge_dispatchers.py','test_rank_money_bridge.py','test_uprising_stubs.py',
             'test_unpack_schedule.py','test_uprising_continuations.py','test_uprising_resource_forks.py']
    results={}
    for version in ['uprising-1.0ea','uprising-1.0','uprising-1.01']:
        directory=OUT/version
        run(selfcheck+['uprising-stubdump',str(directory),version],quiet=True)
        env=os.environ.copy();env['RA3MT_GAME_BUILD']=version;env['RA3MT_STUBS_DIR']=str(directory)
        print('\nBUILD',version,flush=True)
        outputs=[run([sys.executable,'tools/harness/'+script],env) for script in scripts]
        outputs.append(run([sys.executable,'tools/harness/test_spawn_dispatcher.py',str(directory)],env))
        (OUT/(version+'.log')).write_text('\n'.join(outputs),encoding='utf8')
        results[version]={'suites':len(outputs),'status':'passed'}
    run(['dotnet','run','--project','src/RA3MT.UI.SelfCheck','-c','Release','--no-build'])
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
    print('\nPASS: all three builds, ten offline suites per build, static contracts and WPF checks')

if __name__=='__main__':main()
