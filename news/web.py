from lxml import html
from lxml import etree
from csv import reader
import requests
import re
import datetime
import time
from Textanalyse.wordcheck import CheckDict
from pymongo import MongoClient
from stem import Signal
from stem.control import Controller
from multiprocessing import Pool


'''
Init Database connection and set proxy list
'''
client = MongoClient('mongodb://localhost:27017/')
db = client.news_crawler
articles = db.articles
proxies = {
  'http': 'http://127.0.0.1:8123',
  'https': 'http://127.0.0.1:8123',
}
headers = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:51.0) Gecko/20100101 Firefox/51.0'}


def parserec(elements):
    '''
    Recursive function to get the text of an element and all sub elements.
    Necessary because Element.text() and Element.tail() do not return text of child Elements
    :param elements:
    :return:
    '''
    text = ''
    for child in elements:
        # skip elements with tags that contain no necessary information (scripts, comments or specific Elements)
        # TODO make an extra check for img to get alt text
        if child.tag is etree.Comment \
            or child.tag == 'script' \
            or child.tag == 'noscript' \
            or child.tag == 'img' \
        or 'NavFrame searchaux' == child.get("class"):
            continue

        # get text and tail
        ctext = ''
        if child.text is not None:
            ctext = child.text
        ctail = ''
        if child.tail is not None:
            ctail = child.tail

        # next recursive step
        subtext = ''
        if child.getchildren():
            subtext = parserec(child.getchildren())

        text += ctext+' '+subtext+' '+ctail
        text = re.sub(' +',' ',text)

    return text


def parsetext(htmlcontent):
    tree = html.fromstring(htmlcontent)
    element = tree.xpath("//div[@class = 'search-result-items']")
    print(element)
    content = element[0]

    text = parserec(content.getchildren())
    text = re.sub(' +',' ',text)
    wlist = text.split(' ')
    words = {}

    d = CheckDict()

    for w in wlist:
        w = w.replace(',','').replace('(','').replace(')','').replace('\n','').replace('\r','').replace('\xa0','')
        w = re.sub("(/.*)", '', w)
        w = re.sub("(\\.*)", '', w)

        if d.isgerman(w):
            continue

        if w in words:
            words[w] += 1
        else:
            words[w] = 1

    print(words)

    return text


def gettimetag(element):
    '''
    returns the content of the time tag of one lxml html element
    :param element: An lxml htmlElement, can be the time object itself or a parent of the time tag
    :return: Text contents of the time tag or None
    '''
    time = None
    if element.tag == "time":
        return element.get("datetime")
    else:
        if element.getchildren():
            for c in element.getchildren():
                time = gettimetag(c)
                if time is not None:
                    return time

    return time


def get_text(element, css):
    '''
    Get text contents of an element
    :param element: The root element to start the search for the css class of the element to find
    :param css: The css class to identify the text object
    :return: None or the desired text
    '''
    text = None

    if element.get("class") == css:
        return parserec([element])
    else:
        if element.getchildren():
            for child in element.getchildren():
                text = get_text(child, css)
                if text is not None:
                    return text

    return text


def get_element_by_class(el, cl):
    '''
    Searches for an element by class starting from a root node
    :param el: lxml htmlElement. The root node to start the search
    :param cl: the class of the element to find
    :return: None or the first element below el defined by cl
    '''
    element = None

    if el.get("class") == cl:
        return el
    else:
        if el.getchildren():
            for child in el.getchildren():
                element = get_element_by_class(child, cl)
                if element is not None:
                    return element
    return element


def get_teaser(element):
    '''
    Returns the teaser text of an article in search results. Wrapper for get_text
    :param element: lxml htmlElement. The root node to start the search
    :return: The teaser text
    '''
    return get_text(element, 'search-result-story__body')


def get_headline(element):
    '''
    Returns the headline text of an article in search results. Wrapper for get_text
    :param element: lxml htmlElement. The root node to start the serch
    :return:
    '''
    return get_text(element, 'search-result-story__headline')


def find_url(root, parentclass, elclass):
    '''
    Finds a url identified by elclass below parentclass
    :param root: lxml html Element. The root
    :param parentclass: html class tag to search for parent, optional
    :param elclass: html class tag to search for url
    :return:
    '''
    url = None

    if parentclass is not None:
        #try to find parent first by class
        root = get_element_by_class(root, parentclass)

    if elclass is not None:
        #then find link by class
        el = get_element_by_class(root, elclass)
        url = el.get("href")
    else:
        #if elclass is not defined, find the next a in element
        for child in root.getchildren():
            if child.tag == 'a':
                url = child.get("href")
                break

    return url


def get_link(element):
    '''
    Get Link of an article in search results
    :param element:
    :return:
    '''
    return find_url(element,'search-result-story__headline', None)


def has_next_page(root):
    '''
    determines if a search results page contains a "next page" link. The best way to determine if there is further
    results without wasting a request
    :param root:
    :return:
    '''
    pagelink = root.xpath("//div[@class='content-page-links']/a[@class='content-next-link']")

    if len(pagelink) > 0:
        return True

    return False


def renew_connection():
    '''
    Requests a new connection from the local Tor instance. Aka renew IP so we can grab more content without being kicked
    :return:
    '''
    with Controller.from_port(port=9051) as controller:
        controller.authenticate()
        controller.signal(Signal.NEWNYM)


def get_oldest_article(symbol):
    '''
    retrieves the oldest article for a symbol from the database
    :param symbol: The symbol to match
    :return: The Article or none
    '''
    oldest = None
    for article in articles.find({"symbol": symbol}):
        if oldest is None or article['time'] < oldest['time']:
            oldest = article
    return oldest

def run_get_history(args):
    '''
    starts the history crawler with a provided list of arguments, only necessary for pool.map calls with multiple args
    :param args:
    :return:
    '''
    return get_history(*args)


def get_history(search, symbol, sector):
    '''
    The core of our crawler, gets news from the <news source> search. Parses them and saves each article exverpt to the
    database
    :param search: The term to search for
    :param symbol: The symbol this search is related to
    :param sector: The sector this search is related to
    :return: None if everything goes alright, False if there is an error
    '''


    # endtime determines the most recent article included in the search this would be today for recent articles...
    endtime = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    if articles.find({"symbol":symbol}).count() != 0:
        # ... or the date of the oldest article we have in the database if there are already articles
        # <news source> only delivers search results of 50 pages for each search, so to get older articles endtime has to be set
        # accordingly. e.g. a search for today would get all articles up to 50 pages before today
        oldest = get_oldest_article(symbol)
        endtime = oldest["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        # Currently we only check for todays news when we first crawl and for all the other news on later searches
        # TODO if the most recent crawl is older than one day first grab all newer articles

    # prepare the search string to match the url scheme
    search = search.replace(" ", "+")

    print("Get News for " + search)

    searchpage = 1
    tree = None
    news = []
    maxpage = 100   # limits the number of search result pages to crawl (~25 news per page)

    while searchpage <= maxpage:
        # prepare the url
        url = "https://www.<news source>.com/search?query=" + search + "&sort=time:desc&endTime=" + endtime + "&page=" \
              + str(searchpage)
        # send GET request to url using our proxies
        result = requests.get(url, proxies=proxies, headers=headers)
        print("     ",url, result.status_code)  # print result status for debugging
        if result.status_code != 200:
            # if the result was not positive, renew the ip and wait for its changes to take effect
            renew_connection()
            time.sleep(10)
            print("Error searching for", search, symbol, sector)
            return False

        # create a traversable html tree from the GET result
        htmlcontent = result.content.decode('utf-8')
        tree = html.fromstring(htmlcontent)
        elements = tree.xpath(
            "//div[@class = 'search-result-items']/div/article/div[@class = 'search-result-story__container']")

        if len(elements) == 0:
            # the search results were empty. nothing to do here
            return

        for e in elements:
            # get features of each news article element in the element list
            article = {}
            article["time"] = datetime.datetime.strptime(gettimetag(e), '%Y-%m-%dT%H:%M:%S+00:00')
            article["headline"] = get_headline(e)
            article["teaser"] = get_teaser(e)
            article["url"] = get_link(e)
            article["company"] = search
            article["symbol"] = symbol
            article["sector"] = sector
            article["source"] = "<news source>"
            news.append(article)
            # check if the article is already in the database by comparing the url...
            if articles.find_one({"url": article["url"]}) is None:
                # ... and insert it into it if not
                articles.insert_one(article)

        searchpage += 1

        # if the maximum pagecount is not reached and we are on the last page of our search results
        if searchpage <= maxpage and not has_next_page(tree):
            # expand the search to a date further back
            oldest = get_oldest_article(symbol)
            endtime = oldest["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    print(" ",len(news), searchpage)




def crawl_parallel(companies):
    '''
    !!!!WARNING!!!! DO NOT USE THIS
    TODO Parallel execution worked, worker processes were created but only one worker produced network traffic.
     Check if requests.get or proxy block parallel execution

    :param companies:
    :return:
    '''
    pool = Pool(processes=4)
    count = 0
    params = list()
    for comp in companies[1:]:
        # symbol   comp[0]
        # name     comp[2]
        # sector   comp[3]
        #try:
            params.append((comp[2], comp[0], comp[3]))
            if count != 0 and count % 4 == 0:
                #run parallel every 4th iteration
                print("run task for", len(params), params)
                results = pool.map(run_get_history, params)
                params = list()
            count += 1
            # get_history(comp[2], comp[0], comp[3])
       # except:
        #    print("Error searching for",comp[2], comp[0], comp[3])

    return True


def crawl_sequential(companies):
    '''
    crawls a list of companies via get_history
    :param companies:
    :return:
    '''
    for comp in companies[1:]:
        # symbol   comp[0]
        # name     comp[2]
        # sector   comp[3]
        try:
            if comp[0] == "MSFT": # only facebook for testing
                get_history(comp[2], comp[0], comp[3])
        except:
            print("Error searching for",comp[2], comp[0], comp[3])

    return True

if __name__=='__main__':
    '''
    get a list of companies from csv then start the crawling process and measure time
    '''
    t1 = time.time()

    file = open("Indicators and Base Information.csv", "rt")
    lines = reader(file, delimiter=';')
    companies = list(lines)

    print("Companies to search:", len(companies))

    # start crawling
    crawl_sequential(companies)

    t2 = time.time()
    print("Elapsed time: %.3fs" % (t2 - t1))