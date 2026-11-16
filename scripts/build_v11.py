"""Кандидат V11: поиск V8, восстановление и защита от повторных числовых ошибок."""
from build_submission import ROOT, build

if __name__=='__main__':
    print(build(ROOT/'dist/psb-submission-v11.zip',
                engine_path=ROOT/'experiments/v11/psb_engine.py',
                solution_path=ROOT/'experiments/stable/solution.py'))
