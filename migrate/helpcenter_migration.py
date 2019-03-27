#!/usr/bin/env python

"""
Migrates the article content from one help center instance to another. This script loops through the list of
categories and will copy the content.

Arguments:
    action - migrate, update, purge, permissions
    start_id (optional) - The category id to start with. This is useful after a restart
    single_run (optional) - Set to true if you want to only run one category

"""
import os
import re
import sys
import tempfile

import requests
from zenpy.lib.api_objects.help_centre_objects import Category, Section, Article, Translation
from zenpy.lib.exception import RecordNotFoundException

from base_migration import BaseMigration


class HelpcenterMigration(BaseMigration):

    URL_PATTERN = '((https?://[a-zA-Z]+\.[a-zA-Z]+\.[a-zA-Z]+)?/hc/en-us/(articles|sections|categories)/[\d\-a-zA-Z]+)'

    HELPCENTER_DOMAIN = os.getenv('ZENDESK_HELPCENTER_DOMAIN', None)

    dest_categories = []
    dest_sections = {}
    dest_articles = {}

    user_segment_cache = {}

    def migrate(self, start_category_id=None, single=False):
        self.populate_dest_categories()

        # Categories
        start = False if start_category_id else True
        for category in self.source_client.help_center.categories():
            if not start and start_category_id == category.id:
                start = True

            if start:
                self.migrate_category(category)
                if single:
                    break

    def migrate_category(self, category):

        print('Migrating category %s - %s' % (category.id, category.name))

        # Look for existing
        category_id = None
        existing = False
        for existing_category in self.dest_categories:
            if category.name == existing_category.name:
                print('- Existing category found for %s' % category.name)
                existing = True
                category_id = existing_category.id

        if not existing:
            new_category = Category(name=category.name,
                                    description=category.description,
                                    position=category.position)
            print('- Creating category %s' % new_category.name)
            category_id = self.target_client.help_center.categories.create(new_category).id

        # Migrate sections
        self.populate_dest_sections(category_id)
        for section in self.source_client.help_center.categories.sections(category_id=category.id):
            self.migrate_section(section, category_id)

        print('')

    def migrate_section(self, source, category_id):
        print('Migrating section %s - %s' % (source.id, source.name))

        # Look for existing
        section_id = None
        existing = False
        for existing_section in self.dest_sections.get(category_id):
            if source.name == existing_section.name and existing_section.category_id == category_id:
                print('- Existing section found for %s' % source.name)
                existing = True
                section_id = existing_section.id

        if not existing:
            new_section = Section(name=source.name,
                                  description=source.description,
                                  position=source.position,
                                  manageable_by=source.manageable_by,
                                  locale=source.locale,
                                  sorting=source.sorting,
                                  category_id=category_id)
            print('- Creating section %s' % source.name)
            section_id = self.target_client.help_center.sections.create(new_section).id

        # Migrate articles
        self.populate_dest_articles(section_id)
        articles = self.source_client.help_center.sections.articles(section=source)
        for article in articles:
            self.migrate_article(article, section_id)

        print('')

    def migrate_article(self, source, section_id):
        print('Migrating article %s - %s' % (source.id, source.name))

        # Look for existing
        existing = False
        for existing_article in self.dest_articles.get(section_id):
            if source.name == existing_article.name and existing_article.section_id == section_id:
                print('- Existing article found for %s' % source.name)
                existing = True

        if not existing:
            article = Article(title=source.title,
                              label_names=source.label_names,
                              comments_disabled=source.comments_disabled,
                              promoted=source.promoted,
                              position=source.position)

            article_body = source.body

            # Attachments
            uploads = []
            for attachment in self.source_client.help_center.attachments(article=source.id):
                url = attachment.content_url
                file_name = attachment.file_name
                content_type = attachment.content_type
                response = requests.get(url)

                with tempfile.TemporaryFile() as tmp_file:
                    tmp_file.write(response.content)
                    tmp_file.seek(0)
                    upload = \
                        self.target_client.help_center.attachments.create_unassociated(attachment=tmp_file,
                                                                                       inline=attachment.inline,
                                                                                       file_name=file_name,
                                                                                       content_type=content_type)
                    print('- Attachment created - %s' % file_name)
                    uploads.append(upload)

                    if attachment.inline:
                        # Search/replace the image
                        article_body = article_body.replace(str(attachment.id), str(upload.id))
                        article_body = \
                            article_body.replace('%s.zendesk.com/hc/article_attachments' % self.SOURCE_INSTANCE,
                                                 '%s.zendesk.com/hc/article_attachments' % self.TARGET_INSTANCE)
                        if self.HELPCENTER_DOMAIN:
                            article_body = \
                                article_body.replace('%s/hc/article_attachments' % self.HELPCENTER_DOMAIN,
                                                     '%s.zendesk.com/hc/article_attachments' % self.TARGET_INSTANCE)

            article.body = article_body

            print('- Creating article %s' % article.title)
            article_id = self.target_client.help_center.articles.create(section=section_id, article=article).id

            # Associate the attachments. The API can only handle 20 at a time
            upload_len = len(uploads)
            if upload_len > 0:
                start = 0
                end = upload_len if upload_len <= 20 else 19
                while start < upload_len:
                    print('- Associating attachments: %s -> %s' % (start, end))
                    self.target_client.help_center.attachments.bulk_attachments(article=article_id,
                                                                                attachments=uploads[start:end])
                    start = end + 1
                    end = upload_len if (upload_len-start) <= 20 else end + 20

        print('')

    def update_article_links(self, start_category_id, single):
        # Categories
        start = False if start_category_id else True
        for category in self.target_client.help_center.categories():
            if not start and start_category_id == category.id:
                start = True

            if start:
                print('Updating links for category %s - %s' % (category.id, category.name))
                for section in self.target_client.help_center.categories.sections(category_id=category.id):
                    print('- Updating links for section %s - %s' % (section.id, section.name))
                    self.update_article_links_for_section(section)

                if single:
                    break

    def update_article_links_for_section(self, section):
        for article in self.target_client.help_center.sections.articles(section=section):
            content = str(article.body)

            # Find all the urls
            print('- Processing article "%s"' % article.title)
            changes = False
            matches = re.findall(self.URL_PATTERN, content)
            for match in matches:
                url = match[0]
                domain = match[1]
                item = match[2]

                print('  - Found URL: %s' % url)

                source_item_id = re.findall('.*/(\d+)', url)[0]

                try:
                    new_id = None
                    if item == 'articles':
                        # Get the old article
                        source_article = self.source_client.help_center.articles(id=source_item_id)
                        article_name = source_article.title

                        # Search for the corresponding article in the new site
                        new_id = self.find_article_for_name(article_name)
                    elif item == 'sections':
                        source_section = self.source_client.help_center.sections(id=source_item_id)
                        section_name = source_section.name

                        # Search for the corresponding article in the new site
                        new_id = self.find_section_for_name(section_name)
                    elif item == 'categories':
                        source_category = self.source_client.help_center.categories(id=source_item_id)
                        category_name = source_category.name

                        # Search for the corresponding article in the new site
                        new_id = self.find_category_for_name(category_name)

                    if new_id:
                        # Search/replace the link
                        new_url = '/hc/en-us/%s/%s' % (item, new_id)
                        print('  - New URL: %s' % new_url)
                        content = content.replace(url, new_url)
                        changes = True
                except RecordNotFoundException as e:
                    print('  - Record not found, probably migrated already')

            if changes:
                print('  - Updating article')
                data = Translation(body=content, locale='en-us')
                self.target_client.help_center.articles.update_translation(article, data)
            else:
                print('  - No changes found')

    def find_article_for_name(self, name):
        article_id = None
        for article in self.target_client.help_center.articles.search(query=name):
            if article.title == name:
                article_id = article.id
                break

        return article_id

    def find_section_for_name(self, name):
        section_id = None
        for section in self.target_client.help_center.sections():
            if section.name == name:
                section_id = section.id
                break

        return section_id

    def find_category_for_name(self, name):
        category_id = None
        for category in self.target_client.help_center.categories():
            if category.name == name:
                category_id = category.id
                break

        return category_id

    def populate_dest_categories(self):
        for category in self.target_client.help_center.categories():
            self.dest_categories.append(category)

    def populate_dest_sections(self, category_id):
        sections = []
        for section in self.target_client.help_center.sections(category_id=category_id):
            sections.append(section)

        self.dest_sections[category_id] = sections

    def populate_dest_articles(self, section_id):
        articles = []
        for article in self.target_client.help_center.articles(section_id=section_id):
            articles.append(article)

        self.dest_articles[section_id] = articles

    def purge_dest(self):
        for category in self.target_client.help_center.categories():
            print('Deleting category %s - %s' % (category.id, category.name))
            self.target_client.help_center.categories.delete(category)

    # This function uses a different api interface because Zenpy doesn't yet include user_segments in the article
    def update_article_permissions(self, start_page=1):
        page_counter = start_page if start_page else 1
        more = True
        while more:
            print('Updating page %s of articles' % page_counter)
            articles = self.get_list_from_api(self.SOURCE_INSTANCE,
                                              '/api/v2/help_center/articles.json',
                                              self.source_auth,
                                              'articles',
                                              page_counter)
            page_counter = page_counter + 1
            if len(articles) > 0:
                for source in articles:
                    source_segment = source.get('user_segment_id')
                    if source_segment:
                        segment_id = self.get_target_user_segment(source_segment)
                        article_id = self.find_article_for_name(source.get('name'))
                        path = '/api/v2/help_center/article/%s.json' % article_id
                        article = self.get_from_api(self.TARGET_INSTANCE, path, self.target_auth, 'article')
                        article['user_segment_id'] = segment_id
                        print('Updating user segment for article %s' % article.get('name'))
                        self.update_at_api(self.TARGET_INSTANCE, path, self.target_auth, article, 'article')
            else:
                more = False

    def get_target_user_segment(self, source_id):
        segment_id = self.user_segment_cache.get(source_id)
        if not segment_id:
            source = self.source_client.help_center.user_segments(id=source_id)
            if source:
                for segment in self.target_client.help_center.user_segments():
                    if segment.name == source.name:
                        segment_id = segment.id

                self.user_cache[source_id] = segment_id

        return segment_id


if __name__ == '__main__':

    helpcenter_migration = HelpcenterMigration()

    action = sys.argv[1] if len(sys.argv) > 1 else 'migrate'
    start_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    single_run = (sys.argv[3] == 'single') if len(sys.argv) > 3 else None

    if action == 'migrate':
        helpcenter_migration.migrate(start_id, single_run)
    elif action == 'update':
        helpcenter_migration.update_article_links(start_id, single_run)
    elif action == 'purge':
        helpcenter_migration.purge_dest()
    elif action == 'permissions':
        helpcenter_migration.update_article_permissions(start_id)

    sys.exit()
