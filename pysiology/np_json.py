import json
import numpy as np
from base64 import b64encode
import bcolz

class ArrayAwareJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bcolz.carray) or isinstance(obj, np.ndarray):
            if obj.dtype == "int16":
                r = [int(v) for v in obj]
                return r
            elif obj.dtype in ("float16", "float32", "float64"):
                r = [np.double(v) for v in obj]
                return r
        return json.JSONEncoder.default(self, obj)


