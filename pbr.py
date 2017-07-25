#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Usage:
  pbr [ --ctl_gw=<ip> | --cuc_gw=<ip> | --cmb_gw=<ip> | --wasu_gw=<ip> ]
  pbr (-h | --help)

Options:
  -h --help          Show this screen.
  --ctl-gw=<ip>      Plase give ctl gateway for this server, If not, do not write.
"""

import sys
import re
import commands

try:
    from docopt import docopt
except ImportError,e:
    ask = raw_input("pip install docopt(Y/n)?") or "y"
    print ask
    if ask.lower() == "y":
        (status, output) = commands.getstatusoutput("pip install docopt")
    else:
        print ("bye~")
        sys.exit (1)
    print status
    if status == 0:
        from docopt import docopt
    else:
        print ("install error")
        sys.exit (1)



def ipGeter():
    (status, output) = commands.getstatusoutput("ip a")
    patt_netip = re.findall(r'inet\s(?P<ip>\d+\.\d+\.\d+\.\d+)\/(?P<netmask>\d+)\sbrd\s\d+\.\d+\.\d+\.\d+\sscope global\s(?P<card>.+)', output)
    return patt_netip

def router(**kwargs):
    print kwargs


def main():
    args = docopt(__doc__, version='Naval Fate 2.0')
    kwargs = {
       'cmb_gw': args['--cmb_gw'],
       'ctl_gw': args['--ctl_gw'],
       'cuc_gw': args['--cuc_gw'],
       'wasu_gw': args['--wasu_gw'],
    }
    #router(**kwargs)
    print ipGeter()

if __name__ == '__main__':
    main()