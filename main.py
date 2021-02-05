import json
import os
import shutil
from time import sleep
from typing import List

import requests
from ceph.exceptions import InvalidArgumentError
from ebooklib import epub
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.select import Select
from bs4 import BeautifulSoup

# Options
options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')

WEBDRIVER_PATH = './webdrivers/chromedriver'
BASE_PATH = r"https://jaomix.ru/category/"
DB_PATH = "db"

with open("res/script.js", "r", encoding="utf-8") as f:
    SCRIPT = f.read()

with open("res/default_style.css", "r", encoding="utf-8") as f:
    DEFAULT_STYLE = f.read()

with open("res/nav_style.css", "r", encoding="utf-8") as f:
    NAV_STYLE = f.read()

with open("res/template.html", "r", encoding="utf-8") as f:
    TEMPLATE = f.read()

class JaomixParser:
    def __init__(self):
        self.driver = webdriver.Chrome(WEBDRIVER_PATH, options=options)

    def close(self):
        self.driver.close()

    def get_metadata(self, url: str):
        uuid = url[len(BASE_PATH):-1]
        if len(uuid) == 0:
            raise InvalidArgumentError("Book's url is not valid.")

        if os.path.exists(os.path.join(self.get_db_path(uuid), "metadata.json")) \
                and input("Found metadata from cache. Would you like to use it [y/n]:") != "n":
            with open(os.path.join(self.get_db_path(uuid), "metadata.json"), "r", encoding="utf-8") as f:
                res = json.load(f)
        else:
            self.driver.get(url)
            sleep(1)

            try:
                selector = Select(self.driver.find_element_by_css_selector('.sel-toc'))

                for i in range(len(selector.options)):
                    selector.select_by_index(i)
                    sleep(0.2)
                sleep(2)
            except NoSuchElementException:
                print("No such selector.")

            res = self.driver.execute_script(SCRIPT)
            res = json.loads(res)

            base_url_path = rf"https://jaomix.ru/{uuid}/"
            title_file_names = []

            for url in res['urls']:
                title_file_name = url[len(base_url_path):-1]
                title_file_names.append(title_file_name)

            res['filenames'] = title_file_names
            res['uuid'] = uuid

        if not os.path.exists(self.get_db_path(uuid)):
            os.mkdir(self.get_db_path(uuid))
            os.mkdir(os.path.join(self.get_db_path(uuid), "html"))
            os.mkdir(os.path.join(self.get_db_path(uuid), "txt"))
            os.mkdir(os.path.join(self.get_db_path(uuid), "epub"))

        with open(os.path.join(self.get_db_path(uuid), "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(res, f)

        if not os.path.exists(self.get_cover_path(uuid)):
            r = requests.get(res['cover_path'], stream=True)
            if r.status_code == 200:
                with open(self.get_cover_path(uuid), 'wb') as f:
                    r.raw.decode_content = True
                    shutil.copyfileobj(r.raw, f)

        return res

    def get_text_from_html(self, filename: str):
        with open(filename, "r", encoding="utf-8") as f:
            html = f.read()

        soup = BeautifulSoup(html, features="html.parser").find_all("div", class_="entry themeform")[0]

        # kill all script and style elements
        for script in soup(["script", "style", "ins", "div"]):
            script.extract()  # rip it out

        text = ""
        for el in soup.find_all("p"):
            text += el.get_text() + "\n"
        return text

    @staticmethod
    def get_db_path(uuid: str):
        return os.path.join(DB_PATH, uuid)

    @staticmethod
    def get_html_path(uuid: str, filename: str):
        return os.path.join(DB_PATH, uuid, "html", filename + ".html")

    @staticmethod
    def get_txt_path(uuid: str, filename: str):
        return os.path.join(DB_PATH, uuid, "txt", filename + ".txt")

    @staticmethod
    def get_epub_path(uuid: str, start_chapter: int, end_chapter):
        return os.path.join(DB_PATH, uuid, "epub", f"{uuid}_{start_chapter}_{end_chapter}.epub")

    @staticmethod
    def get_cover_path(uuid: str):
        return os.path.join(DB_PATH, uuid, "cover.jpg")

    def download_chapters(self, uuid: str, urls: List[str], filenames: List[str], start_chapter: int, end_chapter: int):
        for i in range(start_chapter - 1, end_chapter):
            if os.path.exists(self.get_html_path(uuid, filenames[i])):
                continue

            response = requests.get(urls[i])

            if response.status_code != 200 or len(response.text) == 0:
                print(f"Can't download url: {urls[i]}")
                continue

            with open(self.get_html_path(uuid, filenames[i]), "w", encoding="utf-8") as f:
                f.write(response.text)
            sleep(0.2)

        for filename in filenames[start_chapter - 1 : end_chapter]:
            if os.path.exists(self.get_txt_path(uuid, filename)):
                continue

            with open(self.get_txt_path(uuid, filename), "w", encoding="utf-8") as f:
                f.write(self.get_text_from_html(self.get_html_path(uuid, filename)))

    def create_epub(self, res: dict, start_chapter: int, end_chapter: int):
        self.download_chapters(res['uuid'], res['urls'], res['filenames'], start_chapter, end_chapter)

        book = epub.EpubBook()
        book.set_identifier(f"res['uuid']_{start_chapter}_{end_chapter}")
        book.set_title(f"{res['name']} - [{start_chapter}, {end_chapter}]")
        book.set_language('ru')
        book.add_author(res['author'])
        book.add_metadata('DC', 'description', res['description'])

        default_css = epub.EpubItem(uid="style_default", file_name="style/default.css", media_type="text/css",
                                    content=DEFAULT_STYLE)
        book.add_item(default_css)

        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=NAV_STYLE)
        book.add_item(nav_css)

        book.set_cover("images/cover.jpg", open(self.get_cover_path(res['uuid']), 'rb').read())

        chapters = []

        # about chapter
        about = epub.EpubHtml(title='О книге', file_name='about.xhtml', lang="ru")
        about.content = f"<h1>О книге</h1><p>{res['description']}</p><p><img src='images/cover.jpg' alt='Обложка'/></p>"

        book.add_item(about)

        for i in range(start_chapter - 1, end_chapter):
            with open(self.get_txt_path(res['uuid'], res['filenames'][i]), "r", encoding="utf-8") as f:
                contents = f.read().splitlines()
            content = ""

            for el in contents:
                if len(el) != 0:
                    content += "<p>" + el + "</p>"

            c1 = epub.EpubHtml(title=res['titles'][i], file_name=f"{res['filenames'][i]}.xhtml", lang='ru')

            c1.content = TEMPLATE.replace(r"{{ title }}", res['titles'][i]).replace(r"{{ content }}", content)

            book.add_item(c1)
            chapters.append(c1)

            print(res['titles'][i])

        # define Table Of Contents
        book.toc = chapters

        # add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # basic spine
        book.spine = ['cover', 'nav', about, *chapters]

        # write to the file
        epub.write_epub(self.get_epub_path(res['uuid'], start_chapter, end_chapter), book, {})

    def download_epub(self, url: str):
        res = self.get_metadata(url)
        print(f"Total chapters count: {len(res['titles'])}")

        try:
            start_chapter = int(input("Enter start chapter number [default: 1]: "))
        except ValueError:
            start_chapter = 1

        try:
            end_chapter = int(input(f"Enter end chapter number [default: {len(res['titles'])}]: "))
        except ValueError:
            end_chapter = len(res['titles'])
        
        self.create_epub(res, start_chapter, end_chapter)

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    parser = JaomixParser()
    url = input("Enter url from jaomix.ru: ")

    parser.download_epub(url)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
