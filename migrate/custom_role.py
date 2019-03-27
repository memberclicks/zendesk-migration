#!/usr/bin/env python

# There is no Zenpy custom role endpoint so we do it live

import csv
import sys

from base_zendesk import BaseZendesk


class CustomRoleManager(BaseZendesk):

    def create_roles(self):

        existing_roles = self.get_list_from_api(self.TARGET_INSTANCE,
                                                '/api/v2/custom_roles.json',
                                                self.target_auth,
                                                'custom_roles')

        with open('custom_roles.csv', 'r') as csvfile:
            csvreader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in csvreader:
                name = row[0]

                # Skip header row
                if name == 'name':
                    continue

                existing = False
                for role in existing_roles:
                    if role.get('name') == name:
                        existing = True
                        print('Skipping, role %s already exists' % name)
                        break

                if not existing:
                    role = {'name': row[0],
                            'description': row[1],
                            'configuration': {'chat_access':                     row[3] == 'True',
                                              'manage_business_rules':           row[4] == 'True',
                                              'manage_dynamic_content':          row[5] == 'True',
                                              'manage_extensions_and_channels':  row[6] == 'True',
                                              'manage_facebook':                 row[7] == 'True',
                                              'organization_editing':            row[8] == 'True',
                                              'organization_notes_editing':      row[9] == 'True',
                                              'ticket_deletion':                 row[10] == 'True',
                                              'view_deleted_tickets':            row[11] == 'True',
                                              'ticket_tag_editing':              row[12] == 'True',
                                              'twitter_search_access':           row[13] == 'True',
                                              'forum_access_restricted_content': row[14] == 'True',
                                              'end_user_list_access':            row[15],
                                              'ticket_access':                   row[16],
                                              'ticket_comment_access':           row[17],
                                              'voice_access':                    row[18] == 'True',
                                              'moderate_forums':                 row[19] == 'True',
                                              'group_access':                    row[20] == 'True',
                                              'light_agent':                     row[21] == 'True',
                                              'end_user_profile_access':         row[22],
                                              'explore_access':                  row[23],
                                              'forum_access':                    row[24],
                                              'macro_access':                    row[25],
                                              'report_access':                   row[26],
                                              'ticket_editing':                  row[27] == 'True',
                                              'ticket_merge':                    row[28] == 'True',
                                              'view_access':                     row[29],
                                              'user_view_access':                row[30]}}

                    print('Creating role %s: %s' % (name, role))
                    self.create_at_api(self.TARGET_INSTANCE,
                                       '/api/v2/custom_roles.json',
                                       self.target_auth,
                                       role,
                                       'custom_role')


if __name__ == '__main__':
    manager = CustomRoleManager()
    sys.exit(manager.create_roles())
