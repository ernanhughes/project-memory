"""Bounded Chapter 4 development comparison; all attempted cases are retained."""
from __future__ import annotations
import argparse
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'experiments' / 'benchmark'))
from memory_baseline.cli import build_baseline, load_tasks
from memory_baseline.config import BaselineConfig, GeneratorConfig
from graph_memory.config import GraphMemoryConfig
from graph_memory.evaluation.adapter import GraphMemorySystem
from graph_memory.evaluation.routing import route_question
from graph_memory.graphrag_backend.microsoft import MicrosoftGraphRAGBackend
from graph_memory.health.checks import check_health, _input_manifest
from graph_memory.provenance.mapping import build_report


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', default='llama3.1:8b')
    parser.add_argument('--run-id', default='ch4-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    parser.add_argument('--conditions', default='best,graph-basic,graph-local,graph-global,graph-drift,graph-routed')
    parser.add_argument('--task-ids', default='')
    parser.add_argument('--graph-timeout', type=int, default=180)
    args = parser.parse_args()
    conditions = args.conditions.split(',')
    allowed = {'best','graph-basic','graph-local','graph-global','graph-drift','graph-routed'}
    if not set(conditions) <= allowed:
        parser.error('unknown condition')
    run = ROOT.parent / 'experiments/benchmark/runs' / args.run_id
    if Path(args.run_id).name != args.run_id:
        parser.error('run-id must be a single directory name')
    run.mkdir(parents=True, exist_ok=False)
    tasks_file = ROOT / 'fixtures/tasks_ch4.json'
    tasks, payload = load_tasks(tasks_file)
    if args.task_ids:
        selected = set(args.task_ids.split(','))
        if not selected <= {t.task_id for t in tasks}:
            parser.error('unknown task-id')
        tasks = [t for t in tasks if t.task_id in selected]
    cfg = replace(BaselineConfig.from_env(), generator=GeneratorConfig(model=args.reader))
    backend = MicrosoftGraphRAGBackend(GraphMemoryConfig.from_env(query_timeout_seconds=args.graph_timeout))
    manifest = backend.manifest()
    snapshot = backend.snapshot()
    provenance = build_report(backend, snapshot, _input_manifest(backend))
    save(run/'graph_snapshot.json', snapshot.to_dict())
    save(run/'provenance.json', provenance.to_dict())
    save(run/'health.json', asdict(check_health(backend)))
    git = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()
    save(run/'manifest.json', {'status':'running', 'evidence_status':'local development; not canonical book result',
         'git_commit':git, 'graph':manifest, 'baseline':asdict(cfg),
         'tasks': [t.task_id for t in tasks], 'conditions':conditions,
         'tasks_sha256':hashlib.sha256(tasks_file.read_bytes()).hexdigest(),
         'code_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [Path(__file__), * (ROOT/'graph_memory').rglob('*.py')] if 'work' not in p.parts},
         'comparison':{'final_context_chars':cfg.context.max_chars,
             'derived_max_fraction':1/3,'raw_passages':'whole passages including headers',
             'source_metrics':'direct raw evidence admitted to final reader',
             'graph_lineage':'separate from admitted evidence',
             'extra_graph_calls':'not controlled; count unavailable',
             'latency_caveat':'shared local Ollama; other experiments may contend'}})
    baseline = build_baseline(cfg)
    results = []
    try:
        system = GraphMemorySystem(baseline, backend, payload['history_source_ids'])
        for task in tasks:
            for condition in conditions:
                mode = ('best' if condition == 'best' else route_question(task.prompt)
                        if condition == 'graph-routed' else condition.removeprefix('graph-'))
                started = time.perf_counter()
                try:
                    answer = system.ask(task, mode)
                    record = asdict(answer)
                    record.update(status='complete', condition=condition, family=task.family)
                except Exception as exc:
                    record = {'task_id':task.task_id,'condition':condition,'family':task.family,
                        'mode':mode,'status':'failed','error':type(exc).__name__+': '+str(exc),
                        'latencies_ms':{'total':round((time.perf_counter()-started)*1000,1)}}
                results.append(record)
                save(run/'cases'/condition/(task.task_id+'.json'), record)
                print(f'{condition} {task.task_id}: {record["status"]}', flush=True)
    finally:
        baseline.close()
        summary = {}
        for condition in conditions:
            cases = [r for r in results if r['condition']==condition]
            groups = defaultdict(list)
            for r in cases:
                for o in r.get('observations',[]):
                    if o['value'] is not None:
                        groups[(r['family'],o['metric'])].append(o['value'])
            summary[condition] = {'attempted':len(cases),'planned':len(tasks),
                'completed':sum(r['status']=='complete' for r in cases),
                'failed':sum(r['status']=='failed' for r in cases),
                'observed_wall_ms':sum(r['latencies_ms']['total'] for r in cases),
                'metrics_successful_cases_only':{f'{f}/{m}':{'mean':sum(v)/len(v),'n':len(v)}
                                                for (f,m),v in groups.items()}}
        unchanged = backend.output_hashes() == manifest.get('output_hashes', manifest.get('current_output_hashes'))
        save(run/'summary.json',{'conditions':summary,'output_unchanged':unchanged,
            'status':'finished' if len(results)==len(tasks)*len(conditions) else 'interrupted',
            'cross_query_consistency':'not inferred from cross-mode agreement',
            'crossover':'not estimated: complete internal call/token costs unavailable'})
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

