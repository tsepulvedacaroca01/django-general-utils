import inspect
import json
import os

from django.core import exceptions
from django.db.models import JSONField
from jsonschema import (
    validate,
    exceptions as jsonschema_exceptions
)


class JSONSchemaField(JSONField):
    """
    JSONSchemaField(
        schema='schemas/jsonschema.example.json',
        default=dict,
        blank=True
    )
    # https://json-schema.org/learn/getting-started-step-by-step
    {
      "title" : "work experience",
      "type" : "object",
      "additionalProperties": false,
      "properties":{
        "data": {"type": "array",
          "items": {
              "properties" : {
                  "job_title": {"type": "string"},
                  "speciality": {"type": "string"},
                  "company": {"type": "string"},
                  "address": {"type": "string"},
                  "date_from": {"type": "string", "format": "date"},
                  "date_to": {"type": "string", "format": "date"}
              }
          }
        }
      }
    }
    """
    def __init__(self, *args, **kwargs):
        self.schema = kwargs.pop('schema', None)
        super().__init__(*args, **kwargs)

    @property
    def _schema_data(self):
        model_file = inspect.getfile(self.model)
        dirname = os.path.dirname(model_file)

        # schema file related to model.py path

        p = os.path.join(dirname, self.schema)

        with open(p, 'r') as file:
            return json.loads(file.read())

    def _validate_schema(self, value):
        # Disable validation when migrations are faked
        if self.model.__module__ == '__fake__':
            return True

        try:
            status = validate(value, self._schema_data)
        except jsonschema_exceptions.ValidationError as e:
            raise exceptions.ValidationError(e.message, code='invalid')

        return status

    def validate(self, value, model_instance):
        super().validate(value, model_instance)

        self._validate_schema(value)

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)

        if value and not self.null:
            self._validate_schema(value)

        return value
