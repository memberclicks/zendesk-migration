
"""
Migrates tickets from one help center instance to another. The default settings will use the incremental
export API to pull tickets. If the status_to_migrate is set to 'not_closed' the regular ticket API
will be used since most incremental tickets are closed or deleted.

Can be run as a script that takes several command line arguments.
The first argument is the action, which can be 'migrate' or 'update'

Migrate
- ticket_id - Single ticket to migrate
    or
- status_to_migrate - a valid status, 'all', or 'not closed'
- filename (optional) - file that contains a list of ticket ids to migrate. Useful for error retries

Update
- field - What field to update. 'cc' or 'comment_attach'
- ticket_id - Single ticket to migrate
"""

import fileinput
import os
import re
import sys
import tempfile
import requests
import time

from zenpy.lib.api_objects import Ticket, Comment
from zenpy.lib.exception import APIException, ZenpyException

from base_migration import BaseMigration


class TicketMigration(BaseMigration):

    TICKET_ERRORS_LOG = 'ticket_errors.log'
    TICKET_START_TIME = os.getenv('ZENDESK_TICKET_START_TIME', 1262304000)

    # The alt instance can be used if the instance domain changed and ticket content needs to be updated
    SOURCE_ALT_INSTANCE = os.getenv('ZENDESK_SOURCE_ALT_INSTANCE', None)

    def main(self, action='migrate', **kwargs):
        start = time.time()

        os.remove(self.TICKET_ERRORS_LOG)
        with open(self.TICKET_ERRORS_LOG, 'w+') as file:
            file.write('Ticket Migration start time %s\n' % start)

        counter = 0

        ticket_id = kwargs.get('ticket_id')
        filename = kwargs.get('filename')
        status = kwargs.get('status')

        if action == 'migrate':
            if ticket_id:
                source_ticket = self.source_client.tickets(id=ticket_id)
                self.migrate(source_ticket, 'all')
                counter += 1
            elif filename:
                for line in fileinput.input(files=filename):
                    source_ticket = self.source_client.tickets(id=line)
                    self.migrate(source_ticket, status, 'all')
                    counter += 1
            else:
                if status == 'not_closed':
                    ticket_generator = self.source_client.tickets()
                else:
                    ticket_generator = self.source_client.tickets.incremental(start_time=self.TICKET_START_TIME)

                for source_ticket in ticket_generator:
                    generated_timestamp = 'N/A'
                    try:
                        generated_timestamp = source_ticket.generated_timestamp
                    except AttributeError:
                        pass

                    self.migrate(source_ticket, status, generated_timestamp)
                    counter += 1

                    if counter % 100 == 0:
                        print('*** Processed %s tickets in % sec' % (counter, (time.time() - start)))

        elif action == 'update':
            update_field = kwargs.get('update_field')
            if ticket_id:
                source_ticket = self.source_client.tickets(id=ticket_id)
                self.update_ticket(source_ticket, update_field)
                counter += 1
            else:
                ticket_generator = self.source_client.tickets()
                for source_ticket in ticket_generator:
                    try:
                        self.update_ticket(source_ticket, update_field)
                    except ZenpyException as z:
                        self.handle_error(z, source_ticket)

        end = time.time()
        print('Complete: processed %s tickets in %s sec' % (counter, (end - start)))

    def migrate(self, source, status_to_migrate, generated_timestamp='N/A'):
        try:
            self.migrate_ticket(source, status_to_migrate)
        except APIException as e:
            if e.response.status_code == 500:
                print('- Internal Server Error creating ticket, retrying')
                time.sleep(60)
                try:
                    self.migrate_ticket(source, status_to_migrate)
                except APIException as e2:
                    self.handle_error(e2, source, generated_timestamp)
            else:
                self.handle_error(e, source, generated_timestamp)
        except ZenpyException as z:
            self.handle_error(z, source, generated_timestamp)

    def handle_error(self, e, source, generated_timestamp='N/A'):
        print('ERROR processing ticket %s: %s (timestamp: %s)' % (source.id, e, generated_timestamp))
        with open(self.TICKET_ERRORS_LOG, 'a') as file:
            file.write('ERROR processing ticket %s: %s\n' % (source.id, e))

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
        ticket.custom_fields = custom_fields

        # Comments
        comments = self.source_client.tickets.comments(source)
        new_comments = []

        for comment in comments:
            new_comment = Comment(created_at=comment.created_at,
                                  html_body=comment.html_body,
                                  public=comment.public,
                                  metadata=comment.metadata)

            # Author
            author_id = comment.author_id
            new_comment.author_id = self.get_target_user_id(author_id)

            # Inline Attachments
            comment_body = comment.html_body
            uploads = []
            matches = re.findall(self.HTML_IMG_TAG_PATTERN, comment_body)
            if len(matches) > 0:

                for match in matches:
                    img_tag = match[0]
                    url = match[1]

                    print('- Found src url in comment: %s' % url)

                    do_upload = False
                    source_domain = '%s.zendesk.com' % self.SOURCE_INSTANCE
                    source_alt_domain = '%s.zendesk.com' % self.SOURCE_ALT_INSTANCE
                    if source_domain in url or source_alt_domain in url:
                        do_upload = True
                        url = url.replace(source_alt_domain, source_domain)
                    elif self.SOURCE_HELPCENTER_DOMAIN in url:
                        do_upload = True

                    if do_upload:
                        response = requests.get(url, auth=self.source_auth)

                        if not response.status_code == 200:
                            print('- ERROR getting attachment %s: %s' % (url, response.status_code))
                            continue

                        file_name = 'attachment'
                        content_disp = response.headers.get('content-disposition')
                        if content_disp:
                            file_name_match = re.search('inline; filename=\"(.*)\"', content_disp)
                            if file_name_match:
                                file_name = file_name_match.group(1)
                            else:
                                continue
                        content_type = response.headers.get('content-type')

                        if self.DEBUG:
                            print('- DEBUG Attachment created - %s' % file_name)
                            comment_body = comment_body.replace(img_tag, '<See Attachment>')
                        else:
                            with tempfile.TemporaryFile() as tmp_file:
                                tmp_file.write(response.content)
                                tmp_file.seek(0)
                                try:
                                    upload = self.target_client.attachments.upload(fp=tmp_file,
                                                                                   target_name=file_name,
                                                                                   content_type=content_type)

                                    print('- Attachment created - %s' % file_name)
                                    comment_body = comment_body.replace(img_tag, '[See Attachment]')
                                    uploads.append(upload.token)

                                except Exception as e:
                                    print('WARN Exception creating attachment %s - %s' % (file_name, e))

                new_comment.html_body = comment_body

            # Non-inline Attachments
            attachments = comment.attachments
            if attachments and len(attachments) > 0:
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
                                print('WARN Exception creating attachment %s - %s' % (file_name, e))

            new_comment.uploads = uploads

            new_comments.append(new_comment)

        ticket.comments = new_comments

        # Submitter
        ticket.submitter_id = self.get_target_user_id(source.submitter_id)

        # Requestor
        requester_id = source.requester_id
        if requester_id:
            requester = self.get_target_user(requester_id)
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
            assignee = self.get_target_user(assignee_id)
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

    def update_ticket(self, source, update_field):

        ticket = self.find_target_ticket_for_original_id(source.id)

        if not ticket:
            print('Target ticket not found for %s' % source.id)
            return 0
        elif ticket.status == 'deleted' or ticket.status == 'closed':
            print('Skipping %s ticket: %s' % (ticket.status, ticket.id))
            return 0

        print('Ticket %s - %s' % (ticket.id, ticket.subject))

        if update_field == 'cc':

            if len(source.collaborator_ids) > 0:
                new_collab_ids = ticket.collaborator_ids
                for collab_id in source.collaborator_ids:
                    new_collab_ids.append(self.get_target_user_id(collab_id))

                ticket.collaborator_ids = new_collab_ids
                self.target_client.tickets.update(ticket)
                print('- Successfully updated collaborators for ticket %s' % ticket.id)
            else:
                print('- No collaborators to update for ticket %s' % ticket.id)

        elif update_field == 'comment_attach':
            for comment in self.target_client.tickets.comments(ticket=ticket):
                if comment.body == 'Inline attachments':
                    print('- Skipping, ticket already updated')
                    return

            uploads = []
            for source_comment in self.source_client.tickets.comments(ticket=source):

                matches = re.findall(self.HTML_IMG_TAG_PATTERN, source_comment.html_body)
                for match in matches:
                    img_tag = match[0]
                    url = match[1]

                    print('- Found src url in comment: %s' % url)

                    do_upload = False
                    source_domain = '%s.zendesk.com' % self.SOURCE_INSTANCE
                    if source_domain in url:
                        do_upload = True
                    elif self.SOURCE_HELPCENTER_DOMAIN in url:
                        do_upload = True

                    if do_upload:
                        response = requests.get(url, auth=self.source_auth)

                        if not response.status_code == 200:
                            print('- ERROR getting attachment %s: %s' % (url, response.status_code))
                            continue

                        file_name = 'attachment'
                        content_disp = response.headers.get('content-disposition')
                        if content_disp:
                            file_name_match = re.search('inline; filename=\"(.*)\"', content_disp)
                            if file_name_match:
                                file_name = file_name_match.group(1)
                            else:
                                continue

                        content_type = response.headers.get('content-type')

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
                                    print('WARN Exception creating attachment %s - %s' % (file_name, e))

            if len(uploads) > 0:
                ticket.comment = Comment(html_body='Inline attachments',
                                         public=False,
                                         uploads=uploads)
                print('- Updating ticket with attachment comment')
                self.target_client.tickets.update(ticket)


if __name__ == '__main__':

    action_arg = sys.argv[1] if len(sys.argv) > 1 else 'migrate'
    kwargs_arg = {}

    arg2 = sys.argv[2] if len(sys.argv) > 2 else None
    arg3 = sys.argv[3] if len(sys.argv) > 3 else None

    migrate = TicketMigration()

    if action_arg == 'migrate':
        if arg2:
            if str.isnumeric(arg2):
                migrate.main(action_arg, ticket_id=arg2)
            else:
                migrate.main(action_arg, status=arg2, filename=arg3)
        else:
            migrate.main(action_arg, status='closed')
    elif action_arg == 'update':
        migrate.main(action_arg, update_field=arg2, ticket_id=arg3)

    sys.exit()
