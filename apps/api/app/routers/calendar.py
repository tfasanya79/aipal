import importlib
import sys

sys.modules[__name__] = importlib.import_module("app.modules.integrations.calendar_router")
