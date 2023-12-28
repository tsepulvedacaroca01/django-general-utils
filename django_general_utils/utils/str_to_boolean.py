import json

def str_to_boolean(value: str, return_value=False) -> bool | str:
    """
    @param value: string value
    """
    if not isinstance(value, str):
        return value

    try:
        return json.loads(value.lower())
    except json.decoder.JSONDecodeError as e:
        if not return_value:
            raise e

    return value
