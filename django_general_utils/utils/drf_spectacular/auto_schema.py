import typing

from drf_spectacular import openapi


class AutoSchema(openapi.AutoSchema):
    def get_tags(self) -> typing.List[str]:
        """ override this for custom behaviour """
        # URL LIKE THIS: /api/v1/subscription/subscription/ where /api/v1/TAG/SUMMARY/
        return [self.path.split('/')[3].capitalize()]

    def get_summary(self):
        """ override this for custom behaviour """
        # URL LIKE THIS: /api/v1/subscription/subscription/ where /api/v1/TAG/SUMMARY/
        basename = self.path.split('/')[4].replace("_", " ").title()

        have_action = hasattr(self, 'view') and hasattr(self.view, 'action')
        have_detail = hasattr(self, 'view') and hasattr(self.view, 'detail') and self.view.detail

        if have_detail and have_action and 'details' not in self.view.action:
            basename = f'{basename} Details'

        if have_action and self.view.action not in self.method_mapping.values():
            basename = f'{basename} {self.view.action.replace("_", " ").title()}'

        return basename
