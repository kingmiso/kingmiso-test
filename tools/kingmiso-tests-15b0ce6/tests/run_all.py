"""Compatibility entry; all original suites still require audited isolation."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_safe import main
if __name__=='__main__':
    raise SystemExit(main(default_suite='legacy81'))
