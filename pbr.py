#!/usr/bin python
# -*- coding: utf-8 -*-

"""Usage:
  pbr [ --ctl-gw=<ip> ] [--cuc-gw=<ip> ] [ --cmb-gw=<ip> ] [ --wasu-gw=<ip> ]
  pbr (-h | --help)

Options:
  -h --help          Show this screen.
  --ctl-gw=<ip>      Plase give ctl gateway for this server, If not, do not write.
"""

import sys, re, requests, os, time
import ipz
import commands

try:
    from docopt import docopt
except ImportError, e:
    ask = raw_input("pip install docopt(Y/n)?") or "y"
    print ask
    if ask.lower() == "y":
        (status, output) = commands.getstatusoutput("pip install docopt")
    else:
        print ("bye~")
        sys.exit(1)
    print status
    if status == 0:
        from docopt import docopt
    else:
        print ("install error")
        sys.exit(1)
'''
电信路由表号：5
联通路由表号：10
移动路由表号：15
华数路由表号：20
'''
CTL_TABLE, CUC_TABLE, CMB_TABLE, WASU_TABLE = 5, 10, 15, 20

'''
在github维护了几个ISP rule列表，以下URL后面加上
'''
ISP_URL = 'https://raw.githubusercontent.com/zhzhdwy/python-pbr/master/'

'''
rule表中0~32767，可使用1~32765.
1~1000：保留为指定客户目的IP，初步为手动维护。
1001~4000：匹配电信明细地址
4001~7000：匹配联通明细地址
7001~9000：匹配移动明细地址
9001~10000：匹配其他明细地址
'''
CTL_PREF, CUC_PREF, CMB_PREF, WASU_PREF = 1001, 4001, 7001, 9001


class Requirements(object):
    def __init__(self, name, gwip):
        super(Requirements, self).__init__()
        self.name = str(name)
        self.gwip = str(gwip)

    # 获取服务器IP、掩码和接口对应关系
    def ipGet(self):
        (status, output) = commands.getstatusoutput("ip a")
        patt_netip = re.findall(
            r'inet\s(?P<ip>\d+\.\d+\.\d+\.\d+)\/(?P<netmask>\d+)\sbrd\s\d+\.\d+\.\d+\.\d+\sscope global\s(?P<card>.+)',
            output)
        if_list = [{'ip': i[0], 'netmask': i[1], 'if': i[2]} for i in patt_netip]
        return if_list

    # 使用主机的子网掩码计算网关和ip是否在一个网段内,网关地址合法性也在这里面做检查
    def ifMatch(self):
        ip_get = self.ipGet()
        ifinfo = {'ip': '', 'nid': '', 'netmask': '', 'gw': '', 'if': '', 'errcode': '', 'errmsg': ''}
        for i in ip_get:
            ip = ipz.ipz(i['ip'], i['netmask'])
            gw = ipz.ipz(self.gwip, i['netmask'])
            # 网关地址不合法
            if gw['errcode']:
                return {'errcode': gw['errcode'], 'errmsg': gw['errmsg']}
            # 网关地址与IP重复
            elif self.gwip == i['ip']:
                return {'errcode': 3, 'errmsg': 'IP_GW_EQUAL'}
            # 网关地址与IP在相同子网
            elif ip['nid']['dotted_decimal'] == gw['nid']['dotted_decimal']:
                ifinfo['ip'] = i['ip']
                ifinfo['nid'] = ip['nid']['dotted_decimal']
                ifinfo['netmask'] = i['netmask']
                ifinfo['gw'] = self.gwip
                ifinfo['if'] = i['if']
                ifinfo['errcode'] = 0
                return ifinfo

    # 为每张路由表生成默认路由和直连路由
    def setRouter(self):
        if_match = self.ifMatch()
        routelist = []
        if self.name == 'CTL':
            routelist.append(
                'ip route add to {}/{} dev {} table {}'.format(if_match['nid'], if_match['netmask'], if_match['if'],
                                                               CTL_TABLE))
            routelist.append(
                'ip route add to 0/0 via {} dev {} table {}'.format(if_match['gw'], if_match['if'], CTL_TABLE))
        elif self.name == 'CUC':
            routelist.append(
                'ip route add to {}/{} dev {} table {}'.format(if_match['nid'], if_match['netmask'], if_match['if'],
                                                               CUC_TABLE))
            routelist.append(
                'ip route add to 0/0 via {} dev {} table {}'.format(if_match['gw'], if_match['if'], CUC_TABLE))
        elif self.name == 'CMB':
            routelist.append(
                'ip route add to {}/{} dev {} table {}'.format(if_match['nid'], if_match['netmask'], if_match['if'],
                                                               CMB_TABLE))
            routelist.append(
                'ip route add to 0/0 via {} dev {} table {}'.format(if_match['gw'], if_match['if'], CMB_TABLE))
        elif self.name == 'WASU':
            routelist.append(
                'ip route add to {}/{} dev {} table {}'.format(if_match['nid'], if_match['netmask'], if_match['if'],
                                                               WASU_TABLE))
            routelist.append(
                'ip route add to 0/0 via {} dev {} table {}'.format(if_match['gw'], if_match['if'], WASU_TABLE))
        return routelist

    # 查看/tmp/下有没有对应的文件，没有就下载
    def getRule(self):
        rulefile = '/tmp' + '/' + self.name
        if not os.path.exists(rulefile):
            ruleURL = ISP_URL + self.name
            try:
                r = requests.get(ruleURL, timeout=3)
            except requests.exceptions.ConnectTimeout:
                return {'errcode': 4, 'errmsg': 'ISP_URL_CONNECT_TIMEOUT'}
            segment = r.content.split('\n')
            return segment
        else:
            with open(rulefile, "r") as f:
                segment = f.readlines()
            return segment

    # 为明细路由生成rule条目
    def setRuler(self):
        segmentlist = self.getRule()
        rulelist = []
        ctl_pref, cuc_pref, cmb_pref, wasu_pref = CTL_PREF, CUC_PREF, CMB_PREF, WASU_PREF
        if self.name == 'CTL':
            for segment in segmentlist:
                #支持在ISP网段列表中写备注#
                if '#' in segment or '' == segment:
                    continue
                segment = segment.replace('\n', '')
                rulelist.append('ip rule add to {} table {} pref {}'.format(segment, CTL_TABLE, ctl_pref))
                ctl_pref += 1
        elif self.name == 'CUC':
            for segment in segmentlist:
                if '#' in segment or '' == segment:
                    continue
                segment = segment.replace('\n', '')
                rulelist.append('ip rule add to {} table {} pref {}'.format(segment, CUC_TABLE, cuc_pref))
                cuc_pref += 1
        elif self.name == 'CMB':
            for segment in segmentlist:
                if '#' in segment or '' == segment:
                    continue
                segment = segment.replace('\n', '')
                rulelist.append('ip rule add to {} table {} pref {}'.format(segment, CMB_TABLE, cmb_pref))
                cmb_pref += 1
        elif self.name == 'WASU':
            for segment in segmentlist:
                if '#' in segment or '' == segment:
                    continue
                segment = segment.replace('\n', '')
                rulelist.append('ip rule add to {} table {} pref {}'.format(segment, WASU_TABLE, wasu_pref))
                wasu_pref += 1
        return rulelist

    def executeScript(self):
        routelist, rulelist = self.setRouter(), self.setRuler()
        logfile = open('/var/log/pbr.log', 'a+')
        for route in routelist:
            (status, output) = commands.getstatusoutput(route)
            if status:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                log = "Erroute: {} {} {} in table {}\n".format(timestamp, output, route.split()[4], route.split()[-1])
                logfile.write(log)
        for rule in rulelist:
            print rule
            (status, output) = commands.getstatusoutput(rule)
            if status:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                log = "Errule: {} {} {} in table {} pref {}\n".format(timestamp, output, rule.split()[4], rule.split()[6], rule.split()[6])
                logfile.write(log)



def router(**kwargs):
    gw_kwargs = {name: gwip for name, gwip in kwargs.items() if gwip}
    for name, gwip in gw_kwargs.items():
        pbr = Requirements(name, gwip)
        pbr.executeScript()


def main():
    args = docopt(__doc__, version='Policy Based Routing for Linux 1.0')
    kwargs = {
        'CMB': args['--cmb-gw'],
        'CTL': args['--ctl-gw'],
        'CUC': args['--cuc-gw'],
        'WASU': args['--wasu-gw'],
    }
    router(**kwargs)


if __name__ == '__main__':
    main()
