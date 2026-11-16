"""V11 с контролем полноты источников для сравнения явно названных договоров."""
from build_submission import ROOT, build

if __name__=='__main__':
    print(build(ROOT/'dist/psb-submission-v13.zip',
                engine_path=ROOT/'experiments/v13/psb_engine.py',
                solution_path=ROOT/'experiments/stable/solution.py'))
