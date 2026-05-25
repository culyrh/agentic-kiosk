"""
eunjeon compatibility shim using kiwipiepy.
MeloTTS Korean on Windows에서 eunjeon(MeCab C++ 확장) 대신 사용.
"""
from kiwipiepy import Kiwi

class Mecab:
    def __init__(self):
        self._kiwi = Kiwi()

    def pos(self, text):
        tokens = self._kiwi.tokenize(text)
        return [(t.form, t.tag) for t in tokens]

    def morphs(self, text):
        return [t.form for t in self._kiwi.tokenize(text)]

    def nouns(self, text):
        tokens = self._kiwi.tokenize(text)
        return [t.form for t in tokens if str(t.tag).startswith("N")]
