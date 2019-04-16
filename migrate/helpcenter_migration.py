#!/usr/bin/env python

"""
Migrates the article content from one help center instance to another. This script loops through the list of
categories and will copy the content.

Can be run as a script that takes up to 3 command line arguments, which can be the following:
- action - migrate, update_links, purge, permissions, check, check_and_update
- start_id (optional) - The source category id to start with. This is useful after a restart
- single_run (optional) - Set to true if you want to only run one category

"""
import csv
import os
import re
import sys
import tempfile

import requests
from requests import RequestException
from zenpy.lib.api_objects.help_centre_objects import Category, Section, Article, Translation
from zenpy.lib.exception import RecordNotFoundException

from base_migration import BaseMigration


class HelpcenterMigration(BaseMigration):

    URL_PATTERN = \
        '((https?://[0-9a-zA-Z]+\.[0-9a-zA-Z]+\.[0-9a-zA-Z]+)?/hc/en-us/(articles|sections|categories)/[\d\-a-zA-Z]+)'
    OLD_URL_PATTERN = '(?:https?://[0-9a-zA-Z]+\.[0-9a-zA-Z]+\.[0-9a-zA-Z]+)?/entries/[\d\-a-zA-Z]+'
    HREF_PATTERN = 'href=\"([/\d\-a-zA-Z_\:\.\%\?\=]+)\"'

    TARGET_HELPCENTER_DOMAIN = os.getenv('ZENDESK_TARGET_HELPCENTER_DOMAIN', None)

    REPORT_FILE = 'help-center-report.csv'

    target_categories = []
    target_sections = {}
    target_articles = {}

    user_segment_cache = {}

    def main(self, start_category_id=None, single=False, action='migrate'):
        self.populate_target_categories()

        if action == 'check':
            with open(self.REPORT_FILE, 'w+') as csvfile:
                csvwriter = csv.writer(csvfile, delimiter=',',
                                       quotechar='"', quoting=csv.QUOTE_NONNUMERIC)
                csvwriter.writerow(['category', 'section', 'article', 'type', 'url', 'status'])

        # Categories
        start = False if start_category_id and start_category_id > 0 else True
        for source_category in self.source_client.help_center.categories():
            if not start and start_category_id == source_category.id:
                start = True

            if start:
                self.process_category(source_category, action)
                if single:
                    break

    def process_category(self, source_category, action='migrate'):
        # Look for existing
        category = None
        for existing_category in self.target_categories:
            if source_category.name == existing_category.name:
                print('Found Category %s - %s' % (source_category.id, source_category.name))
                category = existing_category

        if not category:
            new_category = Category(name=source_category.name,
                                    description=source_category.description,
                                    position=source_category.position)
            print('Creating Category for %s - %s' % (source_category.id, source_category.name))
            category = self.target_client.help_center.categories.create(new_category)

        print('')

        # Migrate sections
        self.populate_target_sections(category.id)
        for section in self.source_client.help_center.categories.sections(category_id=source_category.id):
            self.process_section(section, category, action)

        print('')

    def process_section(self, source_section, category, action='migrate'):
        # Look for existing
        section = None
        for existing_section in self.target_sections.get(category.id):
            if source_section.name == existing_section.name and existing_section.category_id == category.id:
                print('Found Section %s - %s' % (source_section.id, source_section.name))
                section = existing_section

        if not section:
            new_section = Section(name=source_section.name,
                                  description=source_section.description,
                                  position=source_section.position,
                                  manageable_by=source_section.manageable_by,
                                  locale=source_section.locale,
                                  sorting=source_section.sorting,
                                  category_id=category.id)
            print('Creating Section for %s - %s' % (source_section.id, source_section.name))
            section = self.target_client.help_center.sections.create(new_section)

        print('')

        # Migrate articles
        self.populate_target_articles(section.id)
        articles = self.source_client.help_center.sections.articles(section=source_section)
        for article in articles:
            if action == 'migrate':
                self.migrate_article(article, section.id)
            elif action == 'check_and_update':
                self.check_article(article, category.name, section, remigrate=True)
            elif action == 'check':
                self.check_article(article, category.name, section)

    def migrate_article(self, source, section_id, force=False):

        # Look for existing
        if not force:
            for existing_article in self.target_articles.get(section_id):
                if source.name == existing_article.name and existing_article.section_id == section_id:
                    print('Found Article %s - %s, not migrating' % (source.id, source.name))
                    return existing_article

        print('Creating Article %s - %s' % (source.id, source.name))
        article = Article(title=source.title,
                          label_names=source.label_names,
                          comments_disabled=source.comments_disabled,
                          promoted=source.promoted,
                          position=source.position)

        article.body = source.body

        # User Segment
        if source.user_segment_id:
            segment_id = self.get_target_user_segment(source.user_segment_id)
            article.user_segment_id = segment_id

        print('- Creating article %s' % article.title)
        article_id = self.target_client.help_center.articles.create(section=section_id, article=article).id
        article = self.target_client.help_center.articles(id=article_id)
        article_body = article.body

        changes = False
        trans = Translation(body=article_body, locale='en-us')

        # Draft status
        if source.draft:
            trans.draft = True
            changes = True

        # Inline Attachments
        matches = re.findall(self.IMG_SRC_PATTERN, article_body)
        for match in matches:
            update_att = False
            url = match
            source_domain = '%s.zendesk.com' % self.SOURCE_INSTANCE
            if match.startswith(source_domain) or \
                    match.startswith('https://%s' % self.SOURCE_HELPCENTER_DOMAIN):
                update_att = True
            elif match.startswith('/attachments'):
                update_att = True
                url = 'https://%s.zendesk.com%s' % (self.SOURCE_INSTANCE, match)

            if update_att:
                response = requests.get(url, auth=self.source_auth)

                if not response.status_code == 200:
                    print('- ERROR getting attachment %s: %s' % (url, response.status_code))
                    continue

                content_disp = response.headers.get('content-disposition')
                file_name = re.search('inline; filename=\"(.*)\"', content_disp).group(1)
                content_type = response.headers.get('content-type')
                with tempfile.TemporaryFile() as tmp_file:
                    tmp_file.write(response.content)
                    tmp_file.seek(0)
                    upload = self.target_client.help_center.attachments.create(article=article,
                                                                               attachment=tmp_file,
                                                                               inline=True,
                                                                               file_name=file_name,
                                                                               content_type=content_type)
                    print('- Attachment created - %s' % file_name)

                    # Search/replace the image
                    changes = True
                    article_body = article_body.replace(match, upload.relative_path)
                    trans.body = article_body

        # Non-inline attachments
        # Attachments
        for attachment in self.source_client.help_center.attachments(article=source.id):
            if not attachment.inline:
                url = attachment.content_url
                file_name = attachment.file_name
                content_type = attachment.content_type
                response = requests.get(url, auth=self.source_auth, allow_redirects=False)

                if not response.status_code == 200:
                    print('- ERROR getting attachment %s: %s' % (url, response.status_code))
                    continue

                with tempfile.TemporaryFile() as tmp_file:
                    tmp_file.write(response.content)
                    tmp_file.seek(0)
                    upload = self.target_client.help_center.attachments.create(article=article,
                                                                               attachment=tmp_file,
                                                                               inline=attachment.inline,
                                                                               file_name=file_name,
                                                                               content_type=content_type)
                    print('- Attachment created - %s' % file_name)

        if changes:
            print('- Updating translation')
            self.target_client.help_center.articles.update_translation(article, trans)
        else:
            print('- No changes found')

        print('')
        return article

    def check_article(self, source, category_name, section, remigrate=False):

        # Look for existing
        article = None
        for existing_article in self.target_articles.get(section.id):
            if source.name == existing_article.name and existing_article.section_id == section.id:
                article = existing_article
                break

        if not article:
            print('Article not found')
            return

        article_body = article.body

        if article_body:

            user_segment = article.user_segment_id
            auth = self.target_auth if user_segment else None

            update_article = False

            matches = re.findall(self.HREF_PATTERN, article_body)
            if len(matches) > 0:
                print('Link URLs for Article: %s - %s' % (article.id, article.name))
                for match in matches:
                    status = 'OK'
                    if self.SOURCE_HELPCENTER_DOMAIN in match:
                        status = 'Points to old help center'
                    else:
                        unreachable = False
                        try:
                            result = requests.get(match, allow_redirects=False, auth=auth)
                            if result.status_code == 301 or result.status_code == 302:
                                status = 'Probably OK, redirect %s' % result.status_code
                            elif not result.status_code == 200:
                                unreachable = True
                                status = 'Unreachable - %s' % result.status_code
                        except RequestException as e:
                            unreachable = True
                            status = 'Unreachable - %s' % e

                        if unreachable:
                            if match.startswith('https://%s' % self.SOURCE_INSTANCE) or \
                                    match.startswith('https://%s' % self.TARGET_HELPCENTER_DOMAIN):
                                update_article = True
                            elif match.startswith('/attachments'):
                                update_article = True

                    print('- %s: %s' % (status, match))
                    if not status == 'OK':
                        with open(self.REPORT_FILE, 'a') as csvfile:
                            csvwriter = csv.writer(csvfile, delimiter=',',
                                                   quotechar='"', quoting=csv.QUOTE_NONNUMERIC)
                            csvwriter.writerow([category_name, section.name, article.name, 'ahref', match, status])

            matches = re.findall(self.IMG_SRC_PATTERN, article_body)
            if len(matches) > 0:
                print('Image Source URLs for Article: %s - %s' % (article.id, article.name))

                for match in matches:
                    status = 'OK'
                    if self.SOURCE_HELPCENTER_DOMAIN in match:
                        status = 'Points to old help center'
                        update_article = True
                    else:
                        unreachable = False
                        if match.startswith('//'):
                            # Weird but probably ok
                            status = 'Probably OK'
                        else:
                            try:
                                result = requests.get(match, allow_redirects=False, auth=auth)
                                if not result.status_code == 200:
                                    unreachable = True
                                    status = 'Unreachable - %s' % result.status_code
                            except RequestException as e:
                                unreachable = True
                                status = 'Unreachable - %s' % e

                        if unreachable:
                            if match.startswith('https://%s' % self.SOURCE_INSTANCE) or \
                                    match.startswith('https://%s' % self.TARGET_HELPCENTER_DOMAIN):
                                update_article = True
                            elif match.startswith('/attachments'):
                                update_article = True

                    print('- %s: %s' % (status, match))
                    if not status == 'OK':
                        with open(self.REPORT_FILE, 'a') as csvfile:
                            csvwriter = csv.writer(csvfile, delimiter=',',
                                                   quotechar='"', quoting=csv.QUOTE_NONNUMERIC)
                            csvwriter.writerow([category_name, section.name, article.name, 'imgsrc', match, status])

            if update_article:
                if remigrate:
                    print('Re-migrating article %s - %s' % (source.name, source.id))
                    self.target_client.help_center.articles.archive(article)
                    self.migrate_article(source, section.id, True)
                else:
                    print('Would re-migrate article %s - %s' % (source.name, source.id))

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
                    print('Updating links for section %s - %s' % (section.id, section.name))
                    for article in self.target_client.help_center.sections.articles(section=section):
                        self.update_article_links_for_article(article)

                if single:
                    break

    def update_article_links_for_article(self, article):

        content = str(article.body)

        # Find all the urls
        print('Updating links for article "%s"' % article.title)
        changes = False

        # Look for the old style urls first
        matches = re.findall(self.OLD_URL_PATTERN, content)
        for match in matches:
            try:
                source_domain = '%s.zendesk.com' % self.SOURCE_INSTANCE
                source_alt_domain = '%s.zendesk.com' % self.SOURCE_ALT_INSTANCE
                url = match.replace(source_alt_domain, source_domain)

                response = requests.get(url, auth=self.source_auth, allow_redirects=False)
                if response.status_code == 301 or response.status_code == 302:
                    url = response.headers.get('location')
                    content = content.replace(match, url)
            except RequestException as e:
                pass

        matches = re.findall(self.URL_PATTERN, content)
        for match in matches:
            url = match[0]
            domain = match[1]
            item = match[2]

            print('- Found URL: %s' % url)

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
                    print('- New URL: %s' % new_url)
                    content = content.replace(url, new_url)
                    changes = True
            except RecordNotFoundException as e:
                print('- Record not found, probably migrated already')

        if changes:
            print('- Updating article')
            data = Translation(body=content, locale='en-us')
            self.target_client.help_center.articles.update_translation(article, data)
        else:
            print('- No changes found')

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

    def populate_target_categories(self):
        for category in self.target_client.help_center.categories():
            self.target_categories.append(category)

    def populate_target_sections(self, category_id):
        sections = []
        for section in self.target_client.help_center.sections(category_id=category_id):
            sections.append(section)

        self.target_sections[category_id] = sections

    def populate_target_articles(self, section_id):
        articles = []
        for article in self.target_client.help_center.articles(section_id=section_id):
            articles.append(article)

        self.target_articles[section_id] = articles

    def purge_target(self):
        for category in self.target_client.help_center.categories():
            print('Deleting category %s - %s' % (category.id, category.name))
            self.target_client.help_center.categories.delete(category)

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

    action_arg = sys.argv[1] if len(sys.argv) > 1 else 'migrate'

    if action_arg == 'migrate' or action_arg == 'check' or action_arg == 'check_and_update':
        start_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        single_run = (sys.argv[3] == '1') if len(sys.argv) > 3 else None
        helpcenter_migration.main(start_id, single_run, action_arg)
    elif action_arg == 'update_links':
        start_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        single_run = (sys.argv[3] == '1') if len(sys.argv) > 3 else None
        helpcenter_migration.update_article_links(start_id, single_run)
    elif action_arg == 'purge':
        helpcenter_migration.purge_target()

    sys.exit()
