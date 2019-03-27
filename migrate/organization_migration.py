import sys
import time

from zenpy.lib.api_objects import Organization
from zenpy.lib.exception import APIException

from base_migration import BaseMigration


class OrganizationMigration(BaseMigration):

    def main(self, org_id=None, update=True):
        start = time.time()

        if org_id:
            source = self.source_client.organizations(id=org_id)
            self.migrate_org(source, update)
        else:
            for source in self.source_client.organizations():
                self.migrate_org(source, update)

        end = time.time()
        print('Migration completed in: %s sec' % (end - start))

    def migrate_org(self, source, update=True):
        print('Migrating org %s - %s' % (source.id, source.name))

        existing = self.find_for_name(source.name)
        if existing:
            migrated = existing.organization_fields.get('migrated')
            if migrated:
                print('- Skippig - Org already migrated')
            else:
                if update:
                    existing.domain_names.extend(source.domain_names)
                    existing.tags.extend(source.tags)

                    if existing.details and source.details:
                            existing.details = existing.details + '\n' + source.details
                    elif not existing.details:
                        existing.details = source.details

                    if existing.notes and source.notes:
                            existing.notes = existing.notes + '\n' + source.notes
                    elif not existing.notes:
                        existing.notes = source.notes

                    existing.organization_fields['migrated'] = True

                    try:
                        self.target_client.organizations.update(existing)
                        print('- Org updated')
                    except APIException as ae:
                        print('***ERROR*** updating org - APIException: %s' % ae)
                else:
                    print('- Skipping - Org exists and update is false')
        else:
            org = Organization(name=source.name,
                               shared_tickets=source.shared_tickets,
                               shared_comments=source.shared_comments,
                               external_id=source.external_id,
                               domain_names=source.domain_names,
                               details=source.details,
                               notes=source.notes,
                               group_id=source.group_id,
                               tags=source.tags,
                               organization_fields={'migrated': True})

            try:
                self.target_client.organizations.create(org)
                print('- Org created')
            except APIException as ae:
                print('***ERROR*** creating org - APIException: %s' % ae)

    def find_for_name(self, name):
        result = None

        # Remove '&' char since they don't search well
        search_name = name.replace('&', '')

        orgs = self.target_client.search(type='organization', name=search_name)
        for org in orgs:
            if org.name == name:
                result = org
                # print('- Organization found for %s' % name)

        return result


if __name__ == '__main__':

    item_id = sys.argv[2] if len(sys.argv) > 2 else None

    migration = OrganizationMigration()
    sys.exit(migration.main(item_id, update_org == 'true'))
