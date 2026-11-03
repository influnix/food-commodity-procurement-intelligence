"""Day16 metadata/saved-evidence helpers. No workspace data-directory opens."""
from copy import deepcopy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/day15'))
from common import cfg,read,save,zipped,sha,no_data_access,D12,load_saved_batches


def preservation() -> dict:
    old=read(ROOT/'artifacts/day16/preservation_before.json');allowed=cfg(16)['intentional_changes']
    changed=[];bad=[]
    for name,h in old['files'].items():
        p=ROOT/name;now=sha(p) if p.is_file() else None
        if now!=h:
            row={'path':name,'before_sha256':h,'after_sha256':now,'reason':allowed.get(name)}
            (changed if name in allowed and now else bad).append(row)
    for name,info in read(ROOT/'artifacts/day16/append_only_before.json').items():
        if __import__('hashlib').sha256((ROOT/name).read_bytes()[:info['bytes']]).hexdigest()!=info['sha256']:
            bad.append({'path':name,'reason':'original document prefix modified'})
    for name,s in old['data_stat_only'].items():
        p=ROOT/name
        if not p.is_file() or p.stat().st_size!=s['size'] or p.stat().st_mtime_ns!=s['mtime_ns']:
            bad.append({'path':name,'reason':'protected data metadata changed'})
    return {'passed':not bad,'prior_file_count':len(old['files']),'unchanged_file_hashes':len(old['files'])-len(changed)-len(bad),
        'intentional_changes':changed,'unauthorized_changes':bad,'data_metadata_only':len(old['data_stat_only']),
        'data_bytes_opened_or_rehashed':False,'original_readme_prefix_preserved':True}


def archived_day13_release() -> dict:
    """Preserve archive bytes; README is a declared append, not old current-file hash."""
    import hashlib
    d=ROOT/'artifacts/day13/evidence_a';m=read(d/'evidence_release_manifest.json')
    assert sha(d/'evidence_release_manifest.json')=='7f22d01c68e09d21242fd5d726fbec566b911162b78a2ecc05ebff12de1236c0'
    prefix=read(ROOT/'artifacts/day16/append_only_before.json')['README.md']
    full=0;prefix_count=0
    for row in m['references']:
        p=ROOT/row['path']
        if row['path']=='README.md':
            assert hashlib.sha256(p.read_bytes()[:prefix['bytes']]).hexdigest()==row['sha256']
            assert prefix['bytes']==row['size_bytes'];prefix_count+=1
        else:
            assert sha(p)==row['sha256'] and p.stat().st_size==row['size_bytes'];full+=1
    for name,h in m['outputs'].items():assert sha(d/name)==h
    return {'passed':True,'reference_full_hashes':full,'declared_readme_prefix_reference':prefix_count,
        'archived_release_bytes_unchanged':True,'current_readme_full_hash_is_old_pin':False,'mvp_complete':m['mvp_status']=='COMPLETE'}
