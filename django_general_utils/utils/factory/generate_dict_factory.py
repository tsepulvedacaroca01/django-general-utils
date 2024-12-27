from datetime import datetime, date, time
from functools import partial
from typing import Any, Dict

from factory import Factory
from factory.base import StubObject


def generate_dict_factory(factory: Factory):
    def convert_dict_from_stub(stub: StubObject) -> Dict[str, Any]:
        stub_dict = stub.__dict__

        for key, value in stub_dict.items():
            if isinstance(value, StubObject):
                stub_dict[key] = convert_dict_from_stub(value)
            elif isinstance(value, datetime):
                stub_dict[key] = datetime.strftime(value, '%Y-%m-%d %H:%M:%S')
            elif isinstance(value, date):
                stub_dict[key] = date.strftime(value, '%Y-%m-%d')
            elif isinstance(value, time):
                stub_dict[key] = time.strftime(value, '%H:%M:%S')

        return stub_dict

    def dict_factory(factory, **kwargs):
        stub = factory.stub(**kwargs)
        stub_dict = convert_dict_from_stub(stub)

        return stub_dict

    return partial(dict_factory, factory)
