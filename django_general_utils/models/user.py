from django.contrib.auth import models as auth_models
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models import QuerySet
from queryable_properties.managers import QueryablePropertiesManagerMixin


class UserQuerySet(QuerySet):
    pass


class UserManager(
    QueryablePropertiesManagerMixin,
    models.Manager.from_queryset(UserQuerySet),
    DjangoUserManager
):
    pass


class AbstractUser(auth_models.AbstractUser):
    objects = UserManager()
