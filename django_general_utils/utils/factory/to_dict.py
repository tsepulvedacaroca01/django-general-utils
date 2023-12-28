from factory import Factory
from typing import Type, Union

from . import generate_dict_factory


def to_dict(cls: Union[Factory, Type[Factory]], fields: list = None, exclude: list = None):
    """
    @param cls: Factory Class
    @param fields: Class to include
    @param exclude: Class to exclude
    @return: dict
    """
    data = generate_dict_factory(cls)()

    if fields is not None:
        data = {
            _key: _value for _key, _value in data.items() if _key in fields
        }
    if exclude is not None:
        data = {
            _key: _value for _key, _value in data.items() if _key not in exclude
        }

    return data
