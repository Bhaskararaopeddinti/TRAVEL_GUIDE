import sys
from pathlib import Path

# Ensure Backend directory is in Python path whether run from root or elsewhere
backend_dir = Path(__file__).resolve().parent / "Backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from Backend.app import app

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
