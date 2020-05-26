import json
import base64
import sys
import os
import gzip


def main(config_file, data_file, data_compz):
    with open(config_file) as f:
        print('Using config file: %s' % config_file)
        c = json.load(f)
    with open(data_file, 'w') as f:
        print('Writing data file: %s' % data_file)
        f.write("DATA1 = '%s'" % base64.b64encode(json.dumps(c)))
    with gzip.GzipFile(data_compz, mode='wb', mtime=0) as z:
        print('Writing compressed data file: %s' % data_compz)
        z.write(json.dumps(c))

if __name__ == '__main__':
    config_file = sys.argv[1]
    data_file = sys.argv[2]
    data_compz = sys.argv[3]
    main(config_file, data_file, data_compz)
