import importlib
import sys

sys.modules[__name__] = importlib.import_module("app.modules.auth.profile_router")
