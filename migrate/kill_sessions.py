#!/usr/bin/env python

"""
Deletes all sessions

"""
import sys

from base_zendesk import BaseZendesk


class SessionKill(BaseZendesk):

    def main(self):

        sessions = self.get_list_from_api(instance=self.SOURCE_INSTANCE,
                                          path='/api/v2/sessions.json',
                                          auth=self.source_auth,
                                          entity_name='sessions')
        counter = 0
        for session in sessions:
            url = '/api/v2/users/%s/sessions/%s.json' % (session.get('user_id'), session.get('id'))
            self.delete_at_api(instance=self.SOURCE_INSTANCE,
                               path=url,
                               auth=self.source_auth)
            print('Deleted session %s' % session.get('id'))
            counter += 1

        print('Deleted %s sessions' % counter)


if __name__ == '__main__':
    session_kill = SessionKill()
    sys.exit(session_kill.main())
