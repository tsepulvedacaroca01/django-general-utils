import json


def file_to_json(directory: str) -> dict:
    """
    convert the content of a file to a json
    @param directory: file address
    @return: dict
    """
    with open(directory, encoding='utf-8') as json_file:
        return json.load(json_file)
