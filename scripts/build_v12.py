"""V11 с ограниченным учётом явно указанных периодов действия редакций."""
from build_submission import ROOT, build

if __name__=='__main__':
    print(build(ROOT/'dist/psb-submission-v12.zip',
                engine_path=ROOT/'experiments/v12/psb_engine.py',
                solution_path=ROOT/'experiments/stable/solution.py'))
