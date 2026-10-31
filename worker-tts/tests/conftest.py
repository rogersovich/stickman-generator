import sys
from pathlib import Path

# worker modules are plain files in worker-tts/, not a package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
