"""V8 с ограниченным восстановлением после ошибок и локальной диагностикой."""
from build_submission import ROOT, build

if __name__=='__main__':
    print(build(ROOT/'dist/psb-submission-v8-recovery.zip',
                engine_path=ROOT/'experiments/stable/psb_engine.py',
                solution_path=ROOT/'experiments/stable/solution.py'))
