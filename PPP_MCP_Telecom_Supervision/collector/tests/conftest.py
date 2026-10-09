"""Les tests du collector tournent TOUJOURS en mode simule.

Un .env de laboratoire (COLLECTOR_MODE=real) peut exister a cote des
tests : on force ici l'environnement avant tout import de
collector.config, que load_dotenv() ne surchargera pas (override=False).
"""

import os

os.environ.setdefault("COLLECTOR_MODE", "simulated")
