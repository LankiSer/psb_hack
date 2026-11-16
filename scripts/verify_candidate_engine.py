"""Прогон общих тестов движка против отдельного кандидата, не против веб-версии."""
import argparse
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests')]
import test_engine

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('engine',type=Path)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('candidate_under_test',args.engine)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    for name,value in list(vars(test_engine).items()):
        if getattr(value,'__module__','')=='psb_engine':
            setattr(test_engine,name,getattr(module,name))
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(test_engine))
    raise SystemExit(0 if result.wasSuccessful() else 1)
