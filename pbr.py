#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Usage:
  pbr [ --ctl=<eth0> | --cuc=<eth0> | --cmb=<eth0> | --wasu=<eth0> ]
  pbr (-h | --help)

Options:
  -h --help     Show this screen.
  --ctl         List newly added packages.
  --cuc         List removed packages.
  --cmb
  --wasu
"""

import os
import ipz
from docopt import docopt



def main():
    arguments = docopt(__doc__, version='Naval Fate 2.0')
    print(arguments)
    #if ipz.ipz('1.1.1.1', '24')['errcode']:
    #    print 1

if __name__ == '__main__':
    main()