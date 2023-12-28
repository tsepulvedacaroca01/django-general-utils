from django.utils.translation import gettext_lazy as _


def unique_fields(
        values: list[dict], unique_fields: list, error: str = _('This field cannot be repeated.'), with_key=False
) -> tuple[bool, list]:
    """
    validates if the id is in the list, if not, it inserts an error
    @param values: list dictionary to validate
    @param unique_fields: Unique fields to validate
    @param error: Error message
    @param with_key: if work with dict or list
    @return: errors list
    """
    if with_key:
        errors = [{} for _ in range(len(values))]
    else:
        errors = [[] for _ in range(len(values))]

    with_error = False

    for _field in unique_fields:
        _values = [_[_field] for _ in values]
        _set_values = set(_values)

        if len(_set_values) != len(_values):
            with_error = True

            repeat = set([_number for _number in _values if _values.count(_number) > 1])
            for _index in range(len(_values)):
                if with_key:
                    _error = {}
                else:
                    _error = []

                if _values[_index] in repeat:
                    if with_key:
                        _error = {f'{_field}': error}
                    else:
                        _error = [error]

                if with_key:
                    errors[_index].update(_error)
                else:
                    errors[_index] += _error

    return with_error, errors
