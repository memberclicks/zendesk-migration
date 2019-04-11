import os

import requests
import requests.auth
from zenpy import Zenpy


class BaseZendesk(object):

    # Source Zendesk
    ZENDESK_SOURCE_EMAIL = os.environ['ZENDESK_SOURCE_EMAIL']
    ZENDESK_SOURCE_PASSWORD = os.environ['ZENDESK_SOURCE_PASSWORD']

    # Target Zendesk
    ZENDESK_TARGET_EMAIL = os.environ['ZENDESK_TARGET_EMAIL']
    ZENDESK_TARGET_PASSWORD = os.environ['ZENDESK_TARGET_PASSWORD']

    SOURCE_INSTANCE = os.environ['ZENDESK_SOURCE_INSTANCE']
    TARGET_INSTANCE = os.environ['ZENDESK_TARGET_INSTANCE']

    URL = 'https://%s.zendesk.com%s'

    source_client = Zenpy(email=ZENDESK_SOURCE_EMAIL,
                          password=ZENDESK_SOURCE_PASSWORD,
                          subdomain=SOURCE_INSTANCE)

    target_client = Zenpy(email=ZENDESK_TARGET_EMAIL,
                          password=ZENDESK_TARGET_PASSWORD,
                          subdomain=TARGET_INSTANCE)

    source_auth = requests.auth.HTTPBasicAuth(ZENDESK_SOURCE_EMAIL, ZENDESK_SOURCE_PASSWORD)
    target_auth = requests.auth.HTTPBasicAuth(ZENDESK_TARGET_EMAIL, ZENDESK_TARGET_PASSWORD)

    # Return a json array of entities. Used for entities that are not in Zenpy
    def get_list_from_api(self, instance, path, auth, entity_name, page=None):

        return_array = []
        next_url = self.URL % (instance, path)

        if page is not None and page > 0:
            if '?' in next_url:
                next_url = '%s&page=%s' % (next_url, page)
            else:
                next_url = '%s?page=%s' % (next_url, page)

        while next_url:
            response = requests.get(next_url, auth=auth)
            response_json = response.json()
            entity_json = response_json.get(entity_name)
            if entity_json is not None and len(entity_json) > 0:
                print('API: Retrieved list of %s with length %s' % (entity_name, len(entity_json)))
                for entity in entity_json:
                    return_array.append(entity)
                    next_url = response_json.get('next_page')
            else:
                next_url = None
                print('API: No %s returned' % entity_name)

            if page is not None and page > 0:
                next_url = None

        return return_array

    def get_from_api(self, instance, path, auth, entity_name):

        return_val = None
        url = self.URL % (instance, path)
        response = requests.get(url, auth=auth)
        if response.status_code == 200:
            response_json = response.json()
            return_val = response_json.get(entity_name)
            # print('API: Retrieved %s for id %s' % (entity_name, return_val.get('id')))
        else:
            print('API: Error retrieving %s, path=%s, status=%s: %s' % (entity_name, url, response.status_code, response.content))

        return return_val

    # Create the json entity. Used for entities that are not in Zenpy
    def create_at_api(self, instance, path, auth, data, entity_name):

        return_val = None
        url = self.URL % (instance, path)
        response = requests.post(url, json={entity_name: data}, auth=auth)
        if response.status_code == 200 or response.status_code == 201:
            response_json = response.json()
            return_val = response_json.get(entity_name).get('id')
            print('API: %s created - id: %s' % (entity_name, return_val))
            # print('DEBUG - create response_json: %s' % response_json)
        else:
            print('API: Error creating %s, status=%s: %s' % (entity_name, response.status_code, response.content))

        return return_val

    # Update the json entity. Used for entities that are not in Zenpy
    def update_at_api(self, instance, path, auth, data, entity_name):

        return_val = None
        url = self.URL % (instance, path)
        response = requests.put(url, json={entity_name: data}, auth=auth)
        if response.status_code == 200:
            response_json = response.json()
            return_val = response_json.get(entity_name).get('id')
            print('API: %s updated - id: %s' % (entity_name, return_val))
            # print('DEBUG - update response_json: %s' % response_json)
        else:
            print('API: Error updating %s, status=%s: %s' % (entity_name, response.status_code, response.content))

        return return_val

    # Delete the json entity. Used for entities that are not in Zenpy
    def delete_at_api(self, instance, path, auth):

        return_val = None
        url = self.URL % (instance, path)
        response = requests.delete(url, auth=auth)
        if not response.status_code == 204:
            print('API: Error deleting, path=%s, status=%s: %s' % (url, response.status_code, response.content))
