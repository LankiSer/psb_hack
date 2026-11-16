"""Проверка уже собранного ZIP тем же автономным контрактом, что и основной сборки."""
import argparse
from pathlib import Path
import shutil
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_submission

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path)
    args=parser.parse_args()
    source=args.archive.resolve(strict=True)
    def use_existing(output):
        shutil.copyfile(source,output)
        return output
    test_submission.build=use_existing
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(test_submission))
    raise SystemExit(0 if result.wasSuccessful() else 1)
