import sys

from zenpy.lib.api_objects import Macro
from zenpy.lib.exception import APIException

from base_migration import BaseMigration


class MacroMigration(BaseMigration):

    def main(self, macro_id=None):

        if macro_id:
            source = self.source_client.macros(id=macro_id)
            self.migrate_macro(source)
        else:
            for source in self.source_client.macros():
                self.migrate_macro(source)

                # if source.active:
                #     print(source.title + ': ' + str(source.actions))

    def migrate_macro(self, source):
        if source.active:

            for existing in self.target_client.macros():
                source_title = 'MIGRATED ' + source.title
                if source_title == existing.title:
                    print('Existing macro found for %s' % source.title)
                    return

            print('Migrating macro %s' % source.title)
            macro = Macro(title='MIGRATED ' + source.title,
                          active=False,
                          position=source.position,
                          description=source.description)

            # Actions
            actions = []
            for source_act in source.actions:
                actions.append(self.get_action(source_act))
            macro.actions = actions

            # Restriction
            source_rest = source.restriction
            if source_rest:
                ids = []
                restr_id = None
                if source_rest.get('type') == 'Group':
                    restr_id = self.get_target_group_id(source_rest.get('id'))

                    source_ids = source_rest.get('ids')
                    for source_id in source_ids:
                        ids.append(self.get_target_group_id(source_id))

                macro.restriction = {'type': source_rest.get('type'), 'id': restr_id}
                if len(ids) > 0:
                    macro.restriction['ids'] = ids

            try:
                self.target_client.macros.create(macro)
                print('Created macro %s' % macro.title)
            except APIException as ae:
                print('ERROR - APIException: %s' % ae)


if __name__ == '__main__':
    item_id = sys.argv[1] if len(sys.argv) > 1 else None

    migrate = MacroMigration()
    sys.exit(migrate.main(item_id))
