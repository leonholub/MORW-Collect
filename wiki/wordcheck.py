from os import listdir
from os.path import isfile, join
import re


class CheckDict:
    '''
    Class containing methods to check if words are in a dictionary
    requires dicts directory
    '''
    def __init__(self):
        self.dictionary = []
        path = 'dicts'
        files = [f for f in listdir(path) if isfile(join(path, f))]


        for file in files:
            with open('dicts/'+file) as f:
                content = f.readlines()

            for word in content:
                word = word.strip()
                word = word.replace("a\"", 'ä').replace("o\"", 'ö').replace("u\"", 'ü')
                word = re.sub("(/.*)", '', word)
                word = re.sub("(\.*)", '', word)
                self.dictionary.append(word)

    def getdict(self):
        return self.dictionary

    def isgerman(self, word):
        if any(word in s for s in self.dictionary):
            return True
        return False

