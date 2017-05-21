# MORW News Grabber

We collect news from a very popular online news site for financial news. Using a list of companies we use the 
site search to get a list of articles and save them to a mongodb instance.
 
Since the website is a bit thin-skinned when it comes to webgrabbers i used a locally installed tor proxy and 
the stem library to control the tor connection https://stem.torproject.org/ 
This is necessary to get a new connection once the website recognizes we are a running a grabber.
For obvious reasons i replaced any mentions of said website with <news source> in the code.

This is a work in progress and not ready for anything, just some ideas i wanted to share. 