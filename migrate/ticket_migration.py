
"""
Migrates tickets from one help center instance to another. The default settings will use the incremental
export API to pull tickets. If the status_to_migrate is set to 'not_closed' the regular ticket API
will be used since most incremental tickets are closed or deleted.

Can be run as a script that takes up to two command line arguments, which can be the following:
- ticket_id - Single ticket to migrate
    or
- status_to_migrate - a valid status, 'all', or 'not closed'
- filename (optional) - file that contains a list of ticket ids to migrate. Useful for error retries
"""

import fileinput
import os
import sys
import tempfile
import requests
import time

from zenpy.lib.api_objects import Ticket, Comment
from zenpy.lib.exception import APIException

from base_migration import BaseMigration


class TicketMigration(BaseMigration):

    TICKET_ERRORS_LOG = 'ticket_errors.log'
    TICKET_START_TIME = os.getenv('ZENDESK_TICKET_START_TIME', 1262304000)
    DEBUG = int(os.getenv('ZENDESK_TICKET_DEBUG', 0)) == 1

    def main(self, ticket_id=None, status_to_migrate='all', filename=None):
        start = time.time()

        os.remove(self.TICKET_ERRORS_LOG)
        with open(self.TICKET_ERRORS_LOG, 'w+') as file:
            file.write('Ticket Migration start time %s\n' % start)

        counter = 0

        if ticket_id:
            source = self.source_client.tickets(id=ticket_id)
            self.migrate(source, status_to_migrate)
            counter += 1
        elif filename:
            for line in fileinput.input(files=filename):
                source = self.source_client.tickets(id=line)
                self.migrate(source, status_to_migrate)
                counter += 1
        else:
            if status_to_migrate == 'not_closed':
                ticket_generator = self.source_client.tickets()
            else:
                ticket_generator = self.source_client.tickets.incremental(start_time=self.TICKET_START_TIME)

            for source in ticket_generator:
                self.migrate(source, status_to_migrate, source.generated_timestamp)
                counter += 1

                if counter % 100 == 0:
                    print('*** Processed %s tickets in % sec' % (counter, (time.time() - start)))

        end = time.time()
        print('Migration complete: processed %s tickets in %s sec' % (counter, (end - start)))

    def migrate(self, source, status_to_migrate, generated_timestamp='N/A'):
        try:
            self.migrate_ticket(source, 'all')
        except APIException as e:
            if e.response.status_code == 500:
                print('- Internal Server Error creating ticket, retrying')
                time.sleep(60)
                try:
                    self.migrate_ticket(source, status_to_migrate)
                except APIException as e2:
                    self.handle_migrate_error(e2, source, generated_timestamp)
            else:
                self.handle_migrate_error(e, source, generated_timestamp)

    def handle_migrate_error(self, e, source, generated_timestamp):
        print('ERROR migrating ticket %s: %s (timestamp: %s)' % (source.id, e, generated_timestamp))
        with open(self.TICKET_ERRORS_LOG, 'a') as file:
            file.write('ERROR migrating ticket %s: %s\n' % (source.id, e))

    def migrate_ticket(self, source, status_to_migrate='all'):

        end_time = 'N/A'
        try:
            end_time = source.generated_timestamp
        except AttributeError:
            pass

        if source.status == 'deleted':
            print('Skipping deleted ticket: %s (timestamp: %s)' % (source.id, end_time))
            return 0

        if (not status_to_migrate == 'all' and not status_to_migrate == 'not_closed' and
            not source.status == status_to_migrate) or \
                (status_to_migrate == 'not_closed' and source.status == 'closed'):
            print('Skipping, ticket status is %s: %s (timestamp: %s)' %
                  (source.status, source.id, end_time))
            return 0

        # Look for an existing ticket
        existing = self.find_target_ticket_for_original_id(source.id)
        if existing:
            # Existing tickets will be updated with the events API
            print('Existing ticket found for %s (timestamp: %s)' % (source.id, end_time))
            return existing.id

        print('Migrating ticket %s - %s' % (source.id, source.subject))

        ticket = Ticket(created_at=source.created_at,
                        updated_at=source.updated_at,
                        subject=source.subject,
                        priority=source.priority,
                        type=source.type,
                        status=source.status,
                        tags=source.tags,
                        recipient=source.recipient,
                        brand_id=self.get_target_brand_id(source.brand_id))

        if source.ticket_form_id:
            ticket.ticket_form_id = self.get_target_ticket_form_id(source.ticket_form_id)

        # Organization
        org_id = source.organization_id
        if org_id:
            new_org_id = self.get_target_org_id(org_id)
            if new_org_id:
                ticket.organization_id = new_org_id

        # Collaborators
        collab_ids = source.collaborator_ids
        new_collab_ids = []
        for collab_id in collab_ids:
            new_collab_ids.append(self.get_target_user_id(collab_id))

        ticket.collaborator_ids = new_collab_ids

        # Custom fields
        source_fields = source.custom_fields
        custom_fields = {}
        for field in source_fields:
            custom_fields[self.get_target_ticket_field_id(field.get('id'))] = field.get('value')
        custom_fields[self.original_id_field] = source.id
        custom_fields[self.original_id_field] = source.id
        ticket.custom_fields = custom_fields

        # Comments
        comments = self.source_client.tickets.comments(source)
        new_comments = []

        for comment in comments:
            # print('Original comment: %s' % comment)
            new_comment = Comment(created_at=comment.created_at,
                                  body=comment.body,
                                  public=comment.public,
                                  metadata=comment.metadata)

            # Author
            author_id = comment.author_id
            new_comment.author_id = self.get_target_user_id(author_id, not self.DEBUG)

            # Attachments
            attachments = comment.attachments
            if attachments and len(attachments) > 0:
                uploads = []
                for attachment in attachments:
                    url = attachment.content_url
                    file_name = attachment.file_name
                    content_type = attachment.content_type
                    response = requests.get(url)

                    if self.DEBUG:
                        print('- DEBUG Attachment created - %s' % file_name)
                    else:
                        with tempfile.TemporaryFile() as tmp_file:
                            tmp_file.write(response.content)
                            tmp_file.seek(0)
                            try:
                                upload = self.target_client.attachments.upload(fp=tmp_file,
                                                                               target_name=file_name,
                                                                               content_type=content_type)

                                print('- Attachment created - %s' % file_name)
                                uploads.append(upload.token)

                            except Exception as e:
                                print('WARN Exception creating attachment %s, continuing' % file_name)

                new_comment.uploads = uploads

            new_comments.append(new_comment)

        ticket.comments = new_comments

        # Submitter
        ticket.submitter_id = self.get_target_user_id(source.submitter_id, not self.DEBUG)

        # Requestor
        requester_id = source.requester_id
        if requester_id:
            requester = self.get_target_user(requester_id, not self.DEBUG)
            if requester:
                if requester.suspended:
                    # End-users can't be assigned tickets
                    comment = Comment(body='Requester was %s (suspended)' % requester.name,
                                      public=False)
                    ticket.comments.append(comment)
                else:
                    ticket.requester_id = requester.id

        # Assignee
        assignee_id = source.assignee_id
        group_id = source.group_id
        if assignee_id:
            assignee = self.get_target_user(assignee_id, not self.DEBUG)
            if assignee:
                if assignee.role == 'end-user':
                    # End-users can't be assigned tickets
                    comment = Comment(body='Assignee was %s (suspended)' % assignee.name,
                                      public=False)
                    ticket.comments.append(comment)
                else:
                    ticket.assignee_id = assignee.id
        elif group_id:
            ticket.group_id = self.get_target_group_id(group_id)

        # Linked source/problem_id
        source_problem_id = source.problem_id
        if source_problem_id:
            problem_ticket = self.find_target_ticket_for_original_id(source_problem_id)
            if problem_ticket:
                if problem_ticket.type == 'problem':
                    print('- Linking existing problem ticket for %s' % source_problem_id)
                    ticket.problem_id = problem_ticket.id
                else:
                    # Can't link them
                    comment = Comment(body='Linked ticket %s is not a problem, could not link' % problem_ticket.id,
                                      public=False)
                    ticket.comments.append(comment)
            else:
                # Migrate the problem ticket
                if self.DEBUG:
                    print('- DEBUG Problem ticket not found, creating for %s' % source_problem_id)
                else:
                    print('- Problem ticket not found, creating for %s' % source_problem_id)
                    source_problem = self.source_client.tickets(id=source_problem_id)
                    ticket.problem_id = self.migrate_ticket(source_problem)
                    # Wait 60 sec for this to show up
                    time.sleep(60)

        new_ticket_id = None
        if self.DEBUG:
            print('- DEBUG Successfully migrated ticket %s to %s (timestamp: %s)' %
                  (source.id, new_ticket_id, end_time))
        else:
            new_ticket_id = self.target_client.ticket_import.create(ticket)
            print('- Successfully migrated ticket %s to %s (timestamp: %s)' % (source.id, new_ticket_id, end_time))

        return new_ticket_id


if __name__ == '__main__':

    arg1 = sys.argv[1] if len(sys.argv) > 1 else None

    ticket_id_arg = None
    status_arg = 'closed'

    if arg1:
        if str.isnumeric(arg1):
            ticket_id_arg = arg1
        else:
            status_arg = arg1

    filename_arg = sys.argv[2] if len(sys.argv) > 2 else None

    migrate = TicketMigration()
    sys.exit(migrate.main(ticket_id_arg, status_arg, filename_arg))
