# -*- coding: utf-8 -*-

import re

decimal_match = re.compile('\d')


def encode_to_utf8(s):
    return s.decode('windows-1251').encode('utf-8')


def encode_to_utf8_ru(x):
    return unicode(x, 'utf8', 'ignore')


def encode_to_utf8_lowercase(s):
    try:
        s = s.decode('utf-8')
    except Exception, err:
        print('Could not decode with utf-8: %s' % err)
    try:
        s = s.decode('windows-1251')
    except Exception, err:
        print('Could not decode with windows-1251: %s' % err)
    s = s.lower().encode('utf-8')
    return s


def bdecode(data):
    """Main function to decode bencoded data"""
    chunks = list(data)
    chunks.reverse()
    root = _dechunk(chunks)
    return root


def _dechunk(chunks):
    item = chunks.pop()

    if item == 'd':
        item = chunks.pop()
        hash_ = {}
        while item != 'e':
            chunks.append(item)
            key = _dechunk(chunks)
            hash_[key] = _dechunk(chunks)
            item = chunks.pop()
        return hash_
    elif item == 'l':
        item = chunks.pop()
        list_ = []
        while item != 'e':
            chunks.append(item)
            list_.append(_dechunk(chunks))
            item = chunks.pop()
        return list_
    elif item == 'i':
        item = chunks.pop()
        num = ''
        while item != 'e':
            num += item
            item = chunks.pop()
        return int(num)
    elif decimal_match.search(item):
        num = ''
        while decimal_match.search(item):
            num += item
            item = chunks.pop()
        line = ''
        for i in range(int(num)):
            line += chunks.pop()
        return line
    return "Invalid input!"
