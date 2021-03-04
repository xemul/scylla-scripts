#!/usr/bin/env python3

import sys

tests = {}
with sys.stdin as f:
    for ln in f:
        x = ln.split()
        if x[2] == 'Starting':
            tests[x[4]] = { 'name': x[5], 'ts': x[0] }
        elif x[2] == 'Test' and x[4] == 'succeeded':
            if not x[3].startswith('#'):
                x[3] = '#' + x[3]
            tests[x[3]+":"]['end'] = x[0]

def toints(ts):
    x = ts.split('.')
    y = x[0].split(':')
    return (int(y[0]), int(y[1]), int(y[2]), int(x[1]))

def timediff(ts, te):
    tsi = toints(ts)
    tei = toints(te)

    msd = tei[3] - tsi[3]
    sd = tei[2] - tsi[2]
    md = tei[1] - tsi[1]
    hd = tei[0] - tsi[0]

    if msd < 0:
        msd += 1000
        sd -= 1
    if sd < 0:
        sd += 60
        md -= 1
    if md < 0:
        md += 60
        hd -= 1

    return (hd * 60 + md) * 60 + sd

for tn in tests:
    t = tests[tn]
    try:
        x = timediff(t['ts'], t['end'])
        print("%s: %d sec" % (t['name'], x))
    except:
        print("%s: not finished?" % tn)
