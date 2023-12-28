from faker.providers import BaseProvider
from localflavor.cl.forms import CLRutField

from .fixtures import RUTS, SANTIAGO_POINTS


class Provider(BaseProvider):
    ruts = RUTS
    santiago_points = SANTIAGO_POINTS

    def rut(self):
        return CLRutField().clean(self.random_element(self.ruts))

    def santiago_point(self):
        return self.random_element(self.santiago_points)
