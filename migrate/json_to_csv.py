#!/usr/bin/env python

"""
Produces a CSV based on the JSON input

"""

import csv
import sys
import json


def create_csv_from_file(args):
    json_filename = args[0]

    json_type = 'normal'
    if len(args) >= 2:
        json_type = args[1]

    with open(json_filename) as json_file:
        json_data = None
        if json_type == 'normal':
            json_data = json.load(json_file)
        elif json_type == 'line':
            json_data = []
            cnt = 1
            for line in json_file:
                print('Loading line %s' % cnt)
                json_data.append(json.loads(line))
                cnt += 1

        if json_data:
            create_csv(json_data, json_filename)


def create_csv(json_data, output_filename):
    with open(output_filename + '.csv', 'w') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=',',
                               quotechar='"', quoting=csv.QUOTE_NONNUMERIC)

        if isinstance(json_data, dict):
            header = []
            for key in json_data.keys():
                value = json_data.get(key)
                if isinstance(value, dict):
                    for sub_key in value.keys():
                        header.append(key + '.' + sub_key)
                else:
                    header.append(key)

            csvwriter.writerow(header)

            row = []
            for key in header:
                value = get_value(json_data, key)
                if isinstance(value, dict):
                    for sub_val in value.values():
                        row.append(sub_val)
                else:
                    row.append(value)

            csvwriter.writerow(row)

        elif isinstance(json_data, list):
            header = []
            for key in json_data[0].keys():
                value = json_data[0].get(key)
                if isinstance(value, dict):
                    for sub_key in value.keys():
                        header.append(key + '.' + sub_key)
                else:
                    header.append(key)

            csvwriter.writerow(header)

            cnt = 1
            for element in json_data:
                row = []
                for key in header:
                    value = get_value(element, key)
                    if isinstance(value, dict):
                        for sub_val in value.values():
                            row.append(sub_val)
                    else:
                        row.append(value)

                print('Writing row %s' % cnt)
                cnt += 1
                csvwriter.writerow(row)


def get_value(json_data, key):
    value = None
    if '.' in key:
        keys = str(key).split('.')
        top_val = json_data.get(keys[0])
        if top_val is not None:
            value = top_val.get(keys[1])
    else:
        value = json_data.get(key)

    return value


if __name__ == '__main__':
    sys.exit(create_csv_from_file(sys.argv[1:]))
