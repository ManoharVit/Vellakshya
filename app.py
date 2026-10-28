"""
Vellakshya PDF Workstation — Production Workstation Entrypoint.
Architect & Lead Developer: Giri Manohar Vemula
LinkedIn: https://www.linkedin.com/in/manoharv511
GitHub: https://github.com/ManoharVit
"""

import os

from app.main import app

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
