from nested_multipart_parser.drf import DrfNestedParser as NestedParser, NestedParser
from rest_framework.exceptions import ParseError
from rest_framework.parsers import MultiPartParser


class DrfNestedParser(MultiPartParser):
    """
    Custom parser that extends DrfNestedParser to handle file uploads.
    It allows nested data structures to be parsed correctly, including files.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        clsDataAndFile = super().parse(stream, media_type, parser_context)

        data = clsDataAndFile.data.dict()
        data.update(clsDataAndFile.files.dict())  # add files to data

        parser = NestedParser(data)
        if parser.is_valid():

            data = parser.validate_data
            all_key_is_digit = all(
                isinstance(key, str) and key.isdigit() for key in data.keys()
            )

            if all_key_is_digit:
                # If all keys are digits, convert to list
                data = list(data.values())

            return data

        raise ParseError(parser.errors)
