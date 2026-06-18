import importlib
import sys

sys.modules[__name__] = importlib.import_module("app.modules.voice.sessions_router")
