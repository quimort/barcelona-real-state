import re

def is_convertible_to_int(value):
    if isinstance(value, str):
        return bool(re.match(r"^-?\d+$", value))
    return False