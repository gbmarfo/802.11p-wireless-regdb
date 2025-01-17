#!/usr/bin/env python

from io import StringIO
import struct
import hashlib
from dbparse import DBParser
import sys

MAGIC = 0x52474442
VERSION = 19

if len(sys.argv) < 3:
    print ('Usage: {0} output-file input-file [key-file]', sys.argv[0])
    sys.exit(2)

def create_rules(countries):
    result = {}
    for c in countries.itervalues():
        for rule in c.permissions:
            result[rule] = 1
    return result.keys()

def create_collections(countries):
    result = {}
    for c in countries.itervalues():
        result[c.permissions] = 1
    return result.keys()


def be32(output, val):
    output.write(struct.pack('>I', val))

class PTR(object):
    def __init__(self, output):
        self._output = output
        self._pos = output.tell()
        be32(output, 0xFFFFFFFF)

    def set(self, val=None):
        if val is None:
            val = self._output.tell()
        self._offset = val
        pos = self._output.tell()
        self._output.seek(self._pos)
        be32(self._output, val)
        self._output.seek(pos)

    def get(self):
        return self._offset

p = DBParser()
countries = p.parse(open(sys.argv[2]))
power = []
bands = []
for c in countries.itervalues():
    for perm in c.permissions:
        if not perm.freqband in bands:
            bands.append(perm.freqband)
        if not perm.power in power:
            power.append(perm.power)
rules = create_rules(countries)
rules.sort(cmp=lambda x, y: cmp(x.freqband, y.freqband))
collections = create_collections(countries)
collections.sort(cmp=lambda x, y: cmp(x[0].freqband, y[0].freqband))

output = StringIO()

# struct regdb_file_header
be32(output, MAGIC)
be32(output, VERSION)
reg_country_ptr = PTR(output)
# add number of countries
be32(output, len(countries))
siglen = PTR(output)

power_rules = {}
for pr in power:
    power_rules[pr] = output.tell()
    pr = [int(v * 100.0) for v in (pr.max_ant_gain, pr.max_eirp)]
    # struct regdb_file_power_rule
    output.write(struct.pack('>II', *pr))

freq_ranges = {}
for fr in bands:
    freq_ranges[fr] = output.tell()
    fr = [int(f * 1000.0) for f in (fr.start, fr.end, fr.maxbw)]
    # struct regdb_file_freq_range
    output.write(struct.pack('>III', *fr))


reg_rules = {}
for reg_rule in rules:
    freq_range, power_rule = reg_rule.freqband, reg_rule.power
    reg_rules[reg_rule] = output.tell()
    # struct regdb_file_reg_rule
    output.write(struct.pack('>III', freq_ranges[freq_range], power_rules[power_rule],
                             reg_rule.flags))


reg_rules_collections = {}

for coll in collections:
    reg_rules_collections[coll] = output.tell()
    # struct regdb_file_reg_rules_collection
    coll = list(coll)
    be32(output, len(coll))
    coll.sort(cmp=lambda x, y: cmp(x.freqband, y.freqband))
    for regrule in coll:
        be32(output, reg_rules[regrule])

# update country pointer now!
reg_country_ptr.set()

countrynames = countries.keys()
countrynames.sort()
for alpha2 in countrynames:
    coll = countries[alpha2]
    # struct regdb_file_reg_country
    output.write(struct.pack('>ccxBI', str(alpha2[0]), str(alpha2[1]), coll.dfs_region, reg_rules_collections[coll.permissions]))


if len(sys.argv) > 3:
    # Load RSA only now so people can use this script
    # without having those libraries installed to verify
    # their SQL changes
    from M2Crypto import RSA

    # determine signature length
    key = RSA.load_key(sys.argv[3])
    hash = hashlib.sha1()
    hash.update(output.getvalue())
    sig = key.sign(hash.digest())
    # write it to file
    siglen.set(len(sig))
    # sign again
    hash = hashlib.sha1()
    hash.update(output.getvalue())
    sig = key.sign(hash.digest())

    output.write(sig)
else:
    siglen.set(0)

outfile = open(sys.argv[1], 'w')
outfile.write(output.getvalue())
