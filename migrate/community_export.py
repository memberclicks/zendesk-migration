#!/usr/bin/env python

"""
Produces a JSON dump of all Community content. Includes the following
- Topics
- Posts
- Post Comments
- Article Comments

"""
import json
import sys

from base_zendesk import BaseZendesk


class CommunityExport(BaseZendesk):

    def main(self):

        topics = self.get_list_from_api(self.SOURCE_INSTANCE,
                                        '/api/v2/community/topics.json',
                                        self.source_auth,
                                        'topics')
        with open('community_topics.json', 'w') as file:
            json.dump(topics, file)

        posts = self.get_list_from_api(self.SOURCE_INSTANCE,
                                       '/api/v2/community/posts.json',
                                       self.source_auth,
                                       'posts')
        with open('community_posts.json', 'w') as file:
            json.dump(posts, file)

        post_comments = []
        for post in posts:
            url = '/api/v2/community/posts/%s/comments.json' % post.get('id')
            post_comments.extend(self.get_list_from_api(self.SOURCE_INSTANCE, url, self.source_auth, 'comments'))

        with open('community_post_comments.json', 'w') as file:
            json.dump(post_comments, file)

        article_comments = []
        for article in self.source_client.help_center.articles():
            url = '/api/v2/help_center/articles/%s/comments.json' % article.id
            article_comments.extend(self.get_list_from_api(self.SOURCE_INSTANCE, url, self.source_auth, 'comments'))

        with open('community_article_comments.json', 'w') as file:
            json.dump(article_comments, file)


if __name__ == '__main__':
    export = CommunityExport()
    sys.exit(export.main())
