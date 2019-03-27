#!/usr/bin/env python

"""
Produces a CSV with a list of all Users in ZenDesk

"""

import sys

from base_zendesk import BaseZendesk
from json_to_csv import create_csv


class UserReport(BaseZendesk):

    def create_report(self):

        users = self.get_list_from_api(self.TARGET_INSTANCE,
                                       '/api/v2/users.json?role[]=agent&role[]=admin',
                                       self.target_auth,
                                       'users')
        create_csv(users, 'users')

        roles = self.get_list_from_api(self.TARGET_INSTANCE,
                                       '/api/v2/custom_roles.json',
                                       self.target_auth,
                                       'custom_roles')
        create_csv(roles, 'custom_roles')

        groups = self.get_list_from_api(self.TARGET_INSTANCE,
                                        '/api/v2/groups.json',
                                        self.target_auth,
                                        'groups')
        create_csv(groups, 'groups')

        group_memberships = self.get_list_from_api(self.TARGET_INSTANCE,
                                                   '/api/v2/group_memberships.json',
                                                   self.target_auth,
                                                   'group_memberships')
        create_csv(group_memberships, 'group_memberships')


if __name__ == '__main__':
    report = UserReport()
    sys.exit(report.create_report())
