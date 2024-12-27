from django import template

register = template.Library()

@register.simple_tag
def dict_get(d: dict, key, default=None):
    """
    Devuelve el valor de la llave `key` en el diccionario `d`.
    Si la llave no existe, retorna `default`.
    """
    return d.get(key, default)
