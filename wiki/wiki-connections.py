from html.parser import HTMLParser
from lxml import html
from lxml import etree
import requests
import re
from wordcheck import CheckDict

'''
Test file to mess with web crawling and html parsing
has methods to find how many links it takes from one wikipedia page to another
or to extract text from wikipedia
'''


class WikiPage:
    """
    Represents a wiki page
    """
    url = None
    content = None

    def __init__(self, url):
        self.url = url
        self.content = requests.get(url).content.decode('utf-8')

    def parserec(self, elements):
        """
        Recursively extracts text from lxml html elements
        """
        text = ''

        for child in elements:
            if child.tag is etree.Comment \
                    or child.tag == 'script' \
                    or child.tag == 'noscript' \
                    or child.tag == 'img' \
                    or 'NavFrame searchaux' == child.get("class"):
                continue
            # make an extra check for img to get alt text
            ctext = ''
            if child.text is not None:
                ctext = child.text

            ctail = ''
            if child.tail is not None:
                ctail = child.tail

            subtext = ''
            if child.getchildren():
                subtext = self.parserec(child.getchildren())

            text += ctext + ' ' + subtext + ' ' + ctail
        return text

    def parsetext(self, htmlcontent):
        """
        Starts recursive parsing of html content to extract plain text from elements
        :param htmlcontent: the html to extract text from
        :return: plain text str
        """
        tree = html.fromstring(htmlcontent)
        element = tree.xpath("//div[@id = 'mw-content-text']")
        content = element[0]

        text = self.parserec(content.getchildren())
        text = re.sub(' +', ' ', text)

        return text

    def get_words(self):
        """
        Experimental method to remove stopwords and return relevant keywords to an article
        :return: Dict
        """
        text = self.parsetext(self.content)
        wlist = text.split(' ')
        words = {}

        d = CheckDict()

        for w in wlist:
            w = w.replace(',', '').replace('(', '').replace(')', '').replace('\n', '').replace('\r', '').replace('\xa0',
                                                                                                                 '')
            w = re.sub("(/.*)", '', w)
            w = re.sub("(\\.*)", '', w)

            if d.isgerman(w):
                continue

            if w in words:
                words[w] += 1
            else:
                words[w] = 1
        return words

    def get_text(self):
        """
        Removes html and returns plain text string of content
        :return: str
        """
        return self.parsetext(self.content)

    def find_links(self):
        """
        Filters all links to other wikipedia sites and returns Dict of all links with page names
        :return: Dict
        """
        links = {}
        tree = html.fromstring(self.content)
        elements = tree.xpath("//div[@id = 'mw-content-text']//a")
        for e in elements:
            target = e.get("href")
            if (
                target is not None
                and '/wiki/' in target
                and 'http' not in target
                and 'Datei:' not in target
                and '.' not in target
                and ':' not in target
            ):
                links[target] = e.text

        return links


class WikiConnections:
    visited = []
    base_url = 'https://de.wikipedia.org'

    def find(self, url, search, depth, maxdepth, trace):
        if depth >= maxdepth or url in self.visited:
            return [], False

        page = WikiPage(url)
        self.visited.append(url)
        trace.append(url)

        links = page.find_links()

        for k, v in links.items():
            if search.lower() in k.lower():
                print('Found ' + search + ' in ' + str(depth) + ' steps')
                return trace, True

        for k, v in links.items():
            snew = str(k)
            t, found = self.find(self.base_url + snew, search, depth + 1, maxdepth, trace=[])
            if found:
                trace = trace + t
                return trace, found

        return [], False

    def find_connections(self):
        max = 7
        t, found = self.find(self.base_url+'/wiki/Apple', 'Deutschland', 0, max, [])

        if found:
            for n in t:
                print(n)
        else:
            print(str(max) + ' steps were not enough')



#p = WikiPage('https://de.wikipedia.org/wiki/Apple')
#print(p.get_text())

con = WikiConnections()
con.find_connections()