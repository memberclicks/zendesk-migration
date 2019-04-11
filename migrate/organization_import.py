#!/usr/bin/env python

"""
Produces a CSV with a list of all Organizations in ZenDesk

"""
import csv
import sys
import urllib.parse

from base_zendesk import BaseZendesk


class OrganizationImport(BaseZendesk):

    def main(self):

        with open('organizations.csv', 'r') as csvfile:
            csvreader = csv.reader(csvfile, delimiter=',',
                                   quotechar='"', quoting=csv.QUOTE_NONNUMERIC)

            header = None
            for row in csvreader:
                name = row[0]
                if not header:
                    header = row
                    continue

                search_name = urllib.parse.quote(name)
                org = None
                for search_org in self.target_client.search(type='organization', name=search_name):
                    if search_org.name == name:
                        print('Organization found for %s' % name)
                        org = search_org
                        break

                if org:
                    for i in range(len(header) - 1):
                        i += 1
                        org.organization_fields[header[i]] = str(row[i])

                    print('Updating org %s' % name)
                    self.target_client.organizations.update(org)
                else:
                    print('WARN - Organization not found for %s' % name)


if __name__ == '__main__':
    org_import = OrganizationImport()
    sys.exit(org_import.main())
