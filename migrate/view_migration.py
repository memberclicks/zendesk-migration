import sys

from zenpy.lib.api_objects import View

from base_migration import BaseMigration


class ViewMigration(BaseMigration):

    def main(self, view_id=None):

        if view_id:
            source = self.source_client.views(id=view_id)
            self.migrate_view(source)
        else:
            for source in self.source_client.views():
                self.migrate_view(source)

                # if source.active:
                #     print(source.title + ': ' + str(source.restriction))

    def migrate_view(self, source):

        if source.active:

            for existing in self.target_client.views():
                source_title = 'MIGRATED ' + source.title
                if source_title == existing.title:
                    print('Existing view found for %s' % source.title)
                    return

            print('Migrating view %s' % source.title)
            view = View(title='MIGRATED ' + source.title,
                        active=False,
                        position=source.position,
                        description=source.description)

            # Execution
            source_ex = source.execution
            execution = {'group_by': source_ex.get('group_by'),
                         'group_order': source_ex.get('group_order'),
                         'sort_by': source_ex.get('sort_by'),
                         'sort_order': source_ex.get('sort_order')}

            columns = []
            for source_col in source_ex.get('columns'):
                column_id = source_col.get('id')
                if column_id == 'ticket_id':
                    column_id = 'nice_id'
                elif isinstance(column_id, int):
                    column_id = self.get_target_ticket_field_id(column_id)

                columns.append(column_id)

            execution['columns'] = columns
            view.output = execution

            # Conditions
            all_cond = []
            for source_all in source.conditions.all:
                all_cond.append(self.get_condition(source_all))

            any_cond = []
            for source_any in source.conditions.any:
                any_cond.append(self.get_condition(source_any))

            conditions = {'all': all_cond, 'any': any_cond}
            view.conditions = conditions

            # Restriction
            source_rest = source.restriction
            if source_rest:
                restr_id = None
                if source_rest.get('type') == 'Group':
                    restr_id = self.get_target_group_id(source_rest.get('id'))
                view.restriction = {'type': source_rest.get('type'), 'id': restr_id}

            print('Creating view %s' % view.title)
            self.target_client.views.create(view)


if __name__ == '__main__':

    item_id = sys.argv[1] if len(sys.argv) > 1 else None

    migrate = ViewMigration()
    sys.exit(migrate.main(item_id))
