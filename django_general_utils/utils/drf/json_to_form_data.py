def json_to_form_data(input_dict, sep="[{i}]"):
    def __flatten(value, prefix, result_dict, previous=None):
        if isinstance(value, dict):
            if previous == "dict":
                prefix += "."

            for key, v in value.items():
                __flatten(v, prefix + key, result_dict, "dict")

        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                __flatten(v, prefix + sep.format(i=i), result_dict, previous)
        else:
            result_dict[prefix] = value

        return result_dict

    return __flatten(input_dict, '', {})
