from django.core.exceptions import ValidationError


class ListValidationError(Exception):
    def __init__(self, messages: list[ValidationError]):
        self.messages = messages

    @property
    def error_list(self):
        return [message.message_dict for message in self.messages]
