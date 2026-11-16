"""Сравнение ошибок области поиска на синтетических контрактах, без вызовов модели."""
import argparse
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests')]
import test_retrieval_scope
from psb_engine import KnowledgeBase, prompt


def measure(engine, prompt_builder):
    test_retrieval_scope.KnowledgeBase = engine
    test_retrieval_scope.prompt = prompt_builder
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_retrieval_scope.RetrievalScopeTests)
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    return {'total':result.testsRun, 'passed':result.testsRun-len(result.failures)-len(result.errors),
            'failures':[case.id().split('.')[-1] for case, _ in result.failures],
            'errors':[case.id().split('.')[-1] for case, _ in result.errors]}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',required=True)
    parser.add_argument('--output',default='dist/scope-v9-comparison.json')
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('baseline_engine',args.baseline)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    report={'baseline':measure(module.KnowledgeBase, module.prompt),'candidate':measure(KnowledgeBase, prompt),
            'scope':'Targeted synthetic regression cases; not platform accuracy or a held-out benchmark.'}
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
