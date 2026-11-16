"""Отдельный кандидат V10: поиск V8, адресная проверка величин в ответе."""
from build_submission import ROOT, build

if __name__=='__main__':
    print(build(ROOT/'dist/psb-submission-v10.zip',engine_path=ROOT/'experiments/v10/psb_engine.py'))
