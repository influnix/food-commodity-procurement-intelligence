"""Create the candidate after complete tests, independent verification and repeat comparison."""
import argparse
import json
from pathlib import Path
from food_procurement_intelligence.evaluation.readiness import freeze_candidate
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('repeat',type=Path);a=p.parse_args()
    print(json.dumps(freeze_candidate(Path.cwd(),a.run.resolve(),a.repeat.resolve()),indent=2))
