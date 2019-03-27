import sys

from zenpy.lib.api_objects import Trigger
from zenpy.lib.exception import APIException

from base_migration import BaseMigration


class TriggerMigration(BaseMigration):
    def main(self, trigger_id=None):

        if trigger_id:
            source = self.source_client.triggers(id=trigger_id)
            self.migrate_trigger(source)
        else:
            for source in self.source_client.triggers():
                self.migrate_trigger(source)

    def migrate_trigger(self, source):
        if source.active:

            for existing in self.target_client.triggers():
                source_title = 'MIGRATED ' + source.title
                if source_title == existing.title:
                    print('Existing trigger found for %s' % source.title)
                    return

            print('Migrating trigger %s' % source.title)
            trigger = Trigger(title='MIGRATED ' + source.title,
                              active=False,
                              position=source.position,
                              description=source.description)

            # Actions
            actions = []
            for source_act in source.actions:
                actions.append(self.get_action(source_act))
            trigger.actions = actions

            # Conditions
            all_cond = []
            for source_all in source.conditions.all:
                all_cond.append(self.get_condition(source_all))

            any_cond = []
            for source_any in source.conditions.any:
                any_cond.append(self.get_condition(source_any))

            conditions = {'all': all_cond, 'any': any_cond}
            trigger.conditions = conditions

            try:
                self.target_client.triggers.create(trigger)
                print('Created trigger %s' % trigger.title)
            except APIException as ae:
                print('ERROR - APIException: %s' % ae)


if __name__ == '__main__':

    item_id = sys.argv[1] if len(sys.argv) > 1 else None

    migrate = TriggerMigration()
    sys.exit(migrate.main(item_id))
