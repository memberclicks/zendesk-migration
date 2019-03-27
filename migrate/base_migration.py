
from zenpy.lib.api_objects import User, Identity
from zenpy.lib.exception import RecordNotFoundException

from base_zendesk import BaseZendesk


class BaseMigration(BaseZendesk):

    ORIGINAL_ID_FIELD_TITLE = 'Original Id'

    original_id_field = None

    user_cache = {}
    org_cache = {}
    group_cache = {}
    ticket_field_cache = {}
    brand_cache = {}
    ticket_form_cache = {}

    def __init__(self) -> None:
        super().__init__()

        # Custom mappings
        # todo - remove hard coded values and add to json
        self.brand_cache['2379186'] = '360000762552'
        self.brand_cache['7709868'] = '360000762552'

        self.ticket_form_cache['35363'] = '360000341912'

        # Set the original id field id
        for field in self.target_client.ticket_fields():
            if field.title == self.ORIGINAL_ID_FIELD_TITLE:
                self.original_id_field = field.id
                break

    def get_target_org_id(self, source_org_id):
        org_id = self.org_cache.get(source_org_id)
        if not org_id:
            try:
                source_org = self.source_client.organizations(id=source_org_id)

                org_id = None
                if source_org:
                    # Remove '&' char since they don't search well
                    search_name = source_org.name.replace('&', '')
                    for org in self.target_client.search(type='organization', name=search_name):
                        if org.name == source_org.name:
                            print('- Organization found for %s' % org.name)
                            self.org_cache[source_org_id] = org.id
                            break
                else:
                    print('ERROR - Organization not found for %s' % source_org.name)

            except RecordNotFoundException as e:
                print('ERROR - Organization not found for %s' % source_org_id)

        return org_id

    def get_target_user_id(self, source_user_id, create=False):
        user_id = self.user_cache.get(source_user_id)
        if not user_id:
            # print('DEBUG - User cache MISS for %s' % user_id)
            source = self.source_client.users(id=source_user_id)
            if source:
                users = self.target_client.search(type='user', email=source.email)
                if users and len(users) > 0:
                    user_id = next(users).id
                    print('- User found for %s' % source.email)
                elif create:
                    new_user = User(email=source.email,
                                    name=source.name,
                                    locale_id=source.locale_id,
                                    phone=source.phone,
                                    role=source.role,
                                    time_zone=source.time_zone,
                                    verified=source.verified,
                                    suspended=source.suspended,
                                    tags=source.tags)
                    if source.organization_id:
                        new_org_id = self.get_target_org_id(source.organization_id)
                        new_user.organization_id = new_org_id
                    print('- Creating user: %s' % new_user.email)
                    created_user = self.target_client.users.create(new_user)
                    user_id = created_user.id

                    if not created_user:
                        print('ERROR - Unable to create user %s' % source.email)

                self.user_cache[source_user_id] = user_id
        # else:
        # print('DEBUG - User cache hit for %s' % user_id)
        return user_id

    def get_target_user(self, source_user_id, create=False):
        user_id = self.user_cache.get(source_user_id)
        user = None
        if not user_id:
            # print('DEBUG - User cache MISS for %s' % user_id)
            source = self.source_client.users(id=source_user_id)
            if source:
                users = self.target_client.search(type='user', email=source.email)
                if users and len(users) > 0:
                    user = next(users)
                    user_id = user.id
                    print('- User found for %s' % source.email)
                elif create:
                    new_user = User(email=source.email,
                                    name=source.name,
                                    locale_id=source.locale_id,
                                    phone=source.phone,
                                    role=source.role,
                                    time_zone=source.time_zone,
                                    verified=source.verified,
                                    suspended=source.suspended,
                                    tags=source.tags)
                    if source.organization_id:
                        new_org_id = self.get_target_org_id(source.organization_id)
                        new_user.organization_id = new_org_id

                    print('- Creating user: %s' % new_user.email)
                    created_user = self.target_client.users.create(new_user)
                    user_id = created_user.id

                    # Identities
                    for source_identity in self.source_client.users.identities(id=source_user_id):
                        if not source_identity.primary:
                            identity = Identity(user_id=user_id,
                                                type=source_identity.type,
                                                value=source_identity.value)
                            self.target_client.users.identities.create(user_id, identity)

                    user = created_user

                    if not created_user:
                        print('ERROR - Unable to create user %s' % source.email)

                self.user_cache[source_user_id] = user_id
        else:
            user = self.target_client.users(id=user_id)

        return user

    def get_target_group_id(self, source_group_id):
        return self.get_target_entity_id('Group',
                                         source_group_id,
                                         self.group_cache,
                                         self.source_client.groups,
                                         self.target_client.groups,
                                         'name')

    def get_target_ticket_field_id(self, source_id):
        return self.get_target_entity_id('Ticket Field',
                                         source_id,
                                         self.ticket_field_cache,
                                         self.source_client.ticket_fields,
                                         self.target_client.ticket_fields,
                                         'title')

    def get_target_ticket_form_id(self, source_id):
        return self.get_target_entity_id('Ticket Form',
                                         source_id,
                                         self.ticket_form_cache,
                                         self.source_client.ticket_forms,
                                         self.target_client.ticket_forms,
                                         'name')

    def get_target_brand_id(self, source_id):
        return self.get_target_entity_id('Brand',
                                         source_id,
                                         self.brand_cache,
                                         self.source_client.brands,
                                         self.target_client.brands,
                                         'name')

    def get_target_entity_id(self, entity_name, source_id, cache, source_func, target_func, comparator):
        entity_id = cache.get(str(source_id))
        if not entity_id:
            entity = source_func(id=source_id)
            value = None
            if comparator == 'name':
                value = entity.name
            elif comparator == 'title':
                value = entity.title

            print('- %s not in cache, retrieving for %s' % (entity_name, value))

            entity_id = None
            if entity:
                entity_list = target_func()
                for new_entity in entity_list:
                    match = False
                    if comparator == 'name':
                        match = new_entity.name == entity.name
                    elif comparator == 'title':
                        match = new_entity.title == entity.title

                    if match:
                        print('- %s found for %s' % (entity_name, value))
                        entity_id = new_entity.id
                        cache[str(source_id)] = entity_id
                        break

                if not entity_id:
                    print('ERROR - %s not found for %s' % (entity_name, value))

        return entity_id

    def find_target_ticket_for_original_id(self, ticket_id):
        result = None
        for ticket in self.target_client.search(type='ticket', fieldvalue=ticket_id):
            for field in ticket.custom_fields:
                if field.get('id') == self.original_id_field and field.get('value') == str(ticket_id):
                    result = ticket

        return result

    def get_condition(self, source):

        field = source.get('field')
        value = source.get('value')

        if field.startswith('custom_fields'):
            field_id = field.rsplit('_')[2]
            field = 'custom_fields_' + str(self.get_target_ticket_field_id(field_id))
        elif str.isnumeric(value):
            if field == 'group_id':
                value = self.get_target_group_id(value)
            elif field == 'brand_id':
                value = self.get_target_brand_id(value)
            elif field == 'assignee_id':
                value = self.get_target_user_id(value)

        return {'field': field,
                'operator': source.get('operator'),
                'value': str(value)}

    def get_action(self, source):

        field = source.get('field')
        value = source.get('value')

        if field.startswith('custom_fields'):
            field_id = field.rsplit('_')[2]
            field = 'custom_fields_' + str(self.get_target_ticket_field_id(field_id))

        elif not isinstance(value, list) and str.isnumeric(value):
            if field == 'group_id':
                value = self.get_target_group_id(value)
            elif field == 'brand_id':
                value = self.get_target_brand_id(value)
            elif field == 'assignee_id':
                value = self.get_target_user_id(value)
            elif field == 'cc':
                value = self.get_target_user_id(value)
            elif field == 'ticket_form_id':
                value = self.get_target_ticket_form_id(value)
            value = str(value)

        return {'field': field,
                'value': value}
