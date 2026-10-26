"""Produce static package evidence. No kubectl, Helm install, Docker build or provider calls."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.m9.package_checks import inspect_docs,inspect_render
from scripts.m9.preflight import CHART,load_values,required_secrets,validate


def save(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def run(argv,commands,cwd=ROOT):
    result=subprocess.run([str(a) for a in argv],cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    commands.append({'argv':[str(a) for a in argv],'cwd':str(cwd.relative_to(ROOT)) if cwd.is_relative_to(ROOT) else 'source-only staging','exit_code':result.returncode})
    return result


EXCLUDE={'.tools','.venv','.env','.git','node_modules','__pycache__','.pytest_cache','test-results','playwright-report','dist','.cache'}
SUFFIXES={'.py','.ps1','.php','.json','.yaml','.yml','.md','.txt','.toml','.tsx','.ts','.mjs','.css','.html','.conf','.tpl','.sql','.sh','.in','.svg','.ttf'}


def source_files():
    """Explicit handoff roots, with generated/private trees removed; no git required."""
    files=[ROOT/name for name in ['README.md','AGENTS.md','blueprint.md','.gitignore','.dockerignore']]
    for name in ['backend','services','contracts','deploy','infra','scripts','frontend','tests','build','.agents','docs/modules']:
        for path in (ROOT/name).rglob('*'):
            rel=path.relative_to(ROOT)
            if any(part in EXCLUDE or part.startswith('pytest-') for part in rel.parts):continue
            if path.is_file() and not path.name.startswith('.env') and (path.suffix in SUFFIXES or path.name in {'Dockerfile','.dockerignore'}):files.append(path)
    files += [ROOT/name for name in ['docs/operations.md','docs/system-design.md','docs/threat-model.md','docs/optional-items.md','docs/workflow-log.md','docs/decisions.md','docs/demo-checklist.md']]
    return sorted(set(p for p in files if p.is_file()))


def check_missing_entrypoints(shell,staging,commands):
    """A missing-source negative must never invoke Docker in the real checkout."""
    (staging/'scripts').mkdir(parents=True)
    shutil.copyfile(ROOT/'scripts/build-images.ps1',staging/'scripts/build-images.ps1')
    return run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',
                staging/'scripts/build-images.ps1','-Module','Backend',
                '-ImagePrefix','urumi','-Tag','review'],commands,staging)


def historical_runtime_comparison():
    prior=json.loads((ROOT/'docs/evidence/m6/image-source-check.json').read_text())
    changed=[];missing=[]
    for name,digest in prior['sha256'].items():
        path=ROOT/name
        if not path.is_file():missing.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=digest:changed.append(name)
    return {'status':'HISTORICAL_COMPARISON_ONLY','files_checked':len(prior['sha256']),
            'different_files':changed,'missing_files':missing,
            'prior_evidence':'docs/evidence/m6/image-source-check.json',
            'scope':'Historical M6 image comparison only; current M10 source freeze and runtime image verification are separate checks.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helm',required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/evidence/m9')
    parser.add_argument('--sentinels',type=Path,help='Optional private JSON object of known sentinel values; content is never printed/copied.')
    args=parser.parse_args();out=args.output.resolve()
    if out==ROOT/'docs/evidence/m9':
        parser.error('Historical M9 evidence is frozen; supply a new --output directory.')
    out.mkdir(parents=True,exist_ok=True)
    helm=shutil.which(args.helm) or str(Path(args.helm).resolve())
    commands=[];summaries={};checks=[]
    def record(number,evidence,detail):checks.append({'id':f'M9-{number:02}','status':'PASS','evidence':evidence,'detail':detail})
    version=run([helm,'version','--short'],commands);assert version.returncode==0,version.stderr
    save(out/'versions.json',{'checked_at':datetime.now(timezone.utc).isoformat(),'python':sys.version.split()[0],'helm':version.stdout.strip(),'PyYAML':__import__('yaml').__version__,'pytest':__import__('pytest').__version__,'jsonschema':__import__('importlib.metadata',fromlist=['version']).version('jsonschema'),'scope':'static checks only'})
    profiles={name:load_values(CHART/f'values-{name}.yaml') for name in ['local','prod']}
    inventory={'components':[
        {'owner':'M2','name':'store/mariadb','build':'build/store/Dockerfile','ports':[80,3306],'evidence':'docs/evidence/m2/report.md'},
        {'owner':'M3','name':'woocommerce-mcp','build':'services/woocommerce_mcp/Dockerfile','ports':[8000],'evidence':'docs/evidence/m3/report.md'},
        {'owner':'M4','name':'inventory-mcp','build':'services/sample_mcps/Dockerfile','ports':[8000],'evidence':'docs/evidence/m4/report.md'},
        {'owner':'M4','name':'Microsoft Learn','build':None,'transport':'external HTTPS Streamable HTTP'},
        {'owner':'M5','name':'platform-db/identity/registry/audits','build':'backend/Dockerfile target checks','ports':[5432],'evidence':'docs/evidence/m5/report.md'},
        {'owner':'M6','name':'gateway','build':'backend/Dockerfile target checks','ports':[8000],'evidence':'docs/evidence/m6/report.md'},
        {'owner':'M7','name':'chat','build':'backend/Dockerfile target checks','evidence':'docs/evidence/m7/report.md','gap':'Real Groq probe pending free-plan confirmation'},
        {'owner':'M8','name':'dashboard','build':'frontend/Dockerfile','ports':[8080],'evidence':'docs/evidence/m8/report.md','gap':'Independent acceptance/user review tracked separately'},
        {'owner':'M10','name':'combined backend','build':'backend/Dockerfile target release','entrypoints_present':all((ROOT/'backend'/n).is_file() for n in ['main.py','orchestrator.py']),'gap':'Build/deployment proof is tracked in M10, not inferred from source presence'}],
        'runtime_contract':profiles['local']['backend'],'mutation_scope':'zero cluster mutations or provider calls'}
    save(out/'component-inventory.json',inventory);record(1,['component-inventory.json'],'All mandatory components and explicit M7/M8/M10 boundaries inventoried.')
    for profile in profiles:
        arguments=['--namespace','urumi','-f',str(CHART/f'values-{profile}.yaml')]
        lint=run([helm,'lint',CHART,*arguments],commands);(out/f'lint-{profile}.txt').write_text(lint.stdout+lint.stderr,encoding='utf-8');assert lint.returncode==0,lint.stderr
        result=run([helm,'template','urumi',CHART,*arguments],commands);assert result.returncode==0,result.stderr
        (out/f'render-{profile}.yaml').write_text(result.stdout,encoding='utf-8');summaries[profile]=inspect_render(result.stdout)
    record(2,['render-local.yaml','render-prod.yaml','lint-local.txt','lint-prod.txt'],'Same chart rendered and linted both complete profiles.')
    tests=run([sys.executable,'-m','pytest','tests/release','-q','-p','no:cacheprovider','--basetemp',str(ROOT/'.tools/m9/pytest-evidence'),'--junitxml',str(out/'tests.xml')],commands)
    (out/'tests.txt').write_text(tests.stdout+tests.stderr,encoding='utf-8');assert tests.returncode==0,'Release tests failed; see tests.txt'
    record(3,['tests.txt','tests.xml'],'Positive and focused negative Helm/schema/preflight/reference cases passed.')
    save(out/'resource-inventory.json',summaries);record(4,['resource-inventory.json'],'Parsed seven workloads, probes/resources and Service/Ingress/config references for both profiles.')
    record(5,['resource-inventory.json','../../operations.md'],'Three retained PVCs and reviewed mount paths; recovery guide includes consistent private backups and isolated restore-first. No live restore claimed.')
    record(6,['resource-inventory.json','tests.txt'],'Parsed allowed/denied policy paths and namespaced RBAC; alternate release/namespace and independent gateway selectors tested. No live enforcement claim.')
    files=source_files();sentinels=[]
    if args.sentinels:
        sentinels=[value for value in json.loads(args.sentinels.read_text()).values() if isinstance(value,str) and value]
    # Evidence is reviewable handoff material too, but is not required in source-only staging.
    evidence_files=[p for p in (ROOT/'docs/evidence').rglob('*') if p.is_file()]
    assert not any(p.name.startswith('.env') or p.suffix.lower() in {'.pem','.key','.p12','.pfx'} or p.name.lower() in {'kubeconfig','kubeconfig.yaml'} for p in evidence_files),'Prohibited private file in evidence'
    matches=[]
    for path in sorted(set(files+evidence_files)):
        content=path.read_bytes()
        if any(value.encode(encoding) in content for value in sentinels for encoding in ['utf-8','utf-16-le','utf-16-be']):matches.append(str(path.relative_to(ROOT)))
    assert not matches,'Known sentinel present in reviewable source; paths only: '+','.join(matches)
    scan={'reviewed_source_file_count':len(files),'reviewed_evidence_file_count':len(evidence_files),'known_private_sentinels_checked':len(sentinels),'matches':len(matches),'prohibited_evidence_files':0,'exclusions':sorted(EXCLUDE),'scope':'explicit source-only handoff roots plus existing evidence; UTF8/UTF16 sentinel bytes checked; unknown-secret absence not guaranteed','files':[str(p.relative_to(ROOT)).replace('\\','/') for p in files]}
    save(out/'source-scan.json',scan);save(out/'secret-inventory.json',{profile:required_secrets(v) for profile,v in profiles.items()})
    record(7,['source-scan.json','secret-inventory.json'],'Names/types/key-names only, Secret-backed consumers and private/generated exclusions; optional known private sentinel scan records its actual count.')
    # Exercise absent entry points in a staged checkout, even after M10 exists.
    shell=shutil.which('pwsh') or shutil.which('powershell')
    assert shell,'PowerShell is required for the build-script rejection check on this host'
    negative=ROOT/('.tools/m9/missing-entrypoint-'+uuid4().hex)
    rejected=check_missing_entrypoints(shell,negative,commands)
    assert rejected.returncode!=0 and 'M10_BACKEND_ENTRYPOINT_MISSING' in rejected.stdout+rejected.stderr
    (out/'backend-build-rejection.txt').write_text(rejected.stdout+rejected.stderr,encoding='utf-8')
    save(out/'runtime-source-parity.json',historical_runtime_comparison())
    pip=run([sys.executable,'-m','pip','check'],commands);assert pip.returncode==0,pip.stderr
    (out/'checker-pip-check.txt').write_text(pip.stdout+pip.stderr,encoding='utf-8')
    save(out/'build-inventory.json',{'standalone_evidence':['docs/evidence/m2/report.md','docs/evidence/m3/report.md','docs/evidence/m4/report.md','docs/evidence/m6/image-source-check.json'],'dashboard':'docs/evidence/m8/report.md (separate module gate)','checks_target':'preserved and source-tested; no old-image rebuild required','combined_backend':'Missing-entrypoint negative rejected in staging before Docker; current release build/deployment not performed by this checker'})
    record(8,['backend-build-rejection.txt','build-inventory.json','runtime-source-parity.json','checker-pip-check.txt','tests.txt'],'Staged missing-source build rejected before Docker; historical source comparison and check-target callers reviewed without claiming current image parity.')
    differences={}
    def diff(a,b,prefix=''):
        if isinstance(a,dict) and isinstance(b,dict):
            for k in a.keys()|b.keys():diff(a.get(k),b.get(k),prefix+'.'+k if prefix else k)
        elif a!=b:differences[prefix]={'local':a,'production':b}
    diff(profiles['local'],profiles['prod']);save(out/'values-differences.json',differences)
    preflight={profile:{'render_errors':validate(v),'deploy_errors':validate(v,'deploy')} for profile,v in profiles.items()}
    assert all(not r['render_errors'] and r['deploy_errors'] for r in preflight.values());save(out/'preflight-examples.json',preflight)
    record(9,['values-differences.json','preflight-examples.json','tests.txt'],'Environment differences recorded, examples render but honestly fail deploy. Metadata-only successful fixture is a unit test, not infrastructure proof.')
    save(out/'documentation-check.json',{'files':inspect_docs(ROOT),'links':'all relative file targets exist','command_scope':'PowerShell/root and Linux/root explicitly separated','future_commands':'M10 labeled; no installation/backup/restore success claimed'})
    record(10,['documentation-check.json'],'Required guides, links and operation caveats checked.')
    staging=ROOT/('.tools/m9/source-only-stage-'+uuid4().hex);staging.mkdir(parents=True,exist_ok=True)
    for path in files:
        target=staging/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    staged_files=list(staging.rglob('*'))
    assert not any(p.name in EXCLUDE or p.name.startswith('.env') for p in staged_files)
    staged=[]
    for profile in profiles:
        result=run([helm,'template','urumi','deploy/charts/urumi','--namespace','urumi','-f',f'deploy/charts/urumi/values-{profile}.yaml'],commands,staging)
        assert result.returncode==0,result.stderr;inspect_render(result.stdout)
        staged.append({'profile':profile,'render_sha256':hashlib.sha256(result.stdout.encode()).hexdigest(),'exit_code':result.returncode})
    save(out/'staging-check.json',{'source_files_copied':len(files),'forbidden_paths':0,'renders':staged,'external_prerequisites':'Host Python and pinned checker dependencies, Helm and PowerShell. No .tools/.env/kubeconfig copied; Docker/build/runtime installation not claimed.'})
    record(11,['staging-check.json'],'Copied source-only package renders both profiles without private environment inputs.')
    checks.append({'id':'M9-12','status':'REVIEW_PENDING','evidence':['acceptance-review.md','acceptance-results.json'],'detail':'Independent read-only review follows; this runner cannot approve itself.'})
    save(out/'commands.json',commands);save(out/'check-results.json',{'status':'PASS_STATIC_REVIEW_PENDING','checks':checks,'cluster_calls':0,'provider_calls':0,'combined_deployment':'not performed'})
    print(json.dumps({'status':'PASS_STATIC_REVIEW_PENDING','checks_passed':11,'independent_review_pending':1,'cluster_calls':0,'provider_calls':0}))


if __name__=='__main__':main()
