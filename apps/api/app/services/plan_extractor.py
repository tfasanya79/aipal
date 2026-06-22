import importlib
import sys

sys.modules[__name__] = importlib.import_module("app.modules.brain.plan_extractor")
