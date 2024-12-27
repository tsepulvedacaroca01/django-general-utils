from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AnonDayThrottle(AnonRateThrottle):
    scope = 'anon_day'


class AnonHourThrottle(AnonRateThrottle):
    scope = 'anon_hour'


class AnonMinThrottle(AnonRateThrottle):
    scope = 'anon_min'


class AnonSecThrottle(AnonRateThrottle):
    scope = 'anon_sec'


class UserDayThrottle(UserRateThrottle):
    scope = 'user_day'


class UserHourThrottle(UserRateThrottle):
    scope = 'user_hour'


class UserMinThrottle(UserRateThrottle):
    scope = 'user_min'


class UserSecThrottle(UserRateThrottle):
    scope = 'user_sec'
