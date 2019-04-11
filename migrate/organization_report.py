#!/usr/bin/env python

"""
Produces a CSV with a list of all Organizations in ZenDesk

"""
import csv
import sys

from base_zendesk import BaseZendesk
from json_to_csv import create_csv


class OrganizationReport(BaseZendesk):

    def create_report(self):

        with open('organizations.csv', 'w') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=',',
                                   quotechar='"', quoting=csv.QUOTE_NONNUMERIC)

            first = True
            for org in self.target_client.organizations():

                fields = org.organization_fields

                if first:
                    print('Writing header')
                    header = ['name']
                    for key in fields:
                        header.append(key)
                    csvwriter.writerow(header)
                    first = False

                print(org.name)
                row = [org.name]
                for key in fields:
                    row.append(fields.get(key))
                csvwriter.writerow(row)


if __name__ == '__main__':
    report = OrganizationReport()
    sys.exit(report.create_report())
