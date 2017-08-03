#!/usr/bin/ python
# -*- coding: utf-8 -*-

"""Usage:
  pbr route (add|update) [ --ctl-gw=<ip> ] [ --cuc-gw=<ip> ] [ --cmb-gw=<ip> ]
  pbr rule remove
  pbr rule update [ ctl ]  [ cuc ]  [ cmb ]
  pbr (-h | --help)
  pbr --version

Options:
  -h --help             脚本帮助页.
  route add             路由添加，在没有路由表中没有路由的情况下添加.
  route update          路由更新，路由表中有默认路由时选择更新操作，更新操作会先删除原有在添加新路由。
  --ctl-gw=<ip>         填写一个电信网关地址.
  --cuc-gw=<ip>         填写一个联通网关地址.
  --cmb-gw=<ip>         填写一个移动网关地址.
  rule remove           策略移除，清除全部策略路由表项。由于一个优先级可以有多个策略，可以使用多次清除rule表。
  rule update           策略更新，默认更新三线所有表项，使用/tmp/,如果没有则去github上下载.使用过其他脚本刷rule表的请清空rule表。
  ctl                   可单独更新电信
  cuc                   可单独更新联通
  cmb                   可单独更新移动
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
脚本日志，报错均放在/var/log/pbr.log中
'''
LOGFILE = '/var/log/pbr.log'

'''
电信缩写CTL，路由表号：5
联通缩写CUC，路由表号：10
移动缩写CMB，路由表号：15
'''

ISP_TABLE = {'CTL': 5,
             'CUC': 10,
             'CMB': 15,
             }

'''
在github维护了几个ISP rule列表，此次定义ISP列表本地维护位置。刷脚本的时候先用本地的，本地没有才会下载。也可以更改以下链接地址。
'''
rule_URL ={'CTL': 'https://raw.githubusercontent.com/zhzhdwy/python-pbr/master/CTL',
          'CUC': 'https://raw.githubusercontent.com/zhzhdwy/python-pbr/master/CUC',
          'CMB': 'https://raw.githubusercontent.com/zhzhdwy/python-pbr/master/CMB',
          }

rule_file = {'CTL': '/tmp/CTL',
            'CUC': '/tmp/CUC',
            'CMB': '/tmp/CMB',
            }

'''
rule表中0~32767，可使用1~32765。10001~20000为更新路由规则区域。
如果要改此pref范围，需要在setRuler()中删除部分也做修改！！
1~1000：保留为指定客户目的IP，初步为手动维护。
1001~4000：匹配电信明细地址，11001~14000电信更新区域
4001~7000：匹配联通明细地址，14001~17000联通更新区域
7001~10000：匹配移动明细地址，17001~19000移动更新区域
'''
ISP_PREF = {'CTL':  {'start': 1001, 'end': 4000},
            'CUC':  {'start': 4001, 'end': 7000},
            'CMB':  {'start': 7001, 'end': 10000},
            }


class RequireRoute(object):
    def __init__(self, ispname, gwip):
        super(RequireRoute, self).__init__()
        self.ispname = str(ispname)
        self.gwip = str(gwip)

# 获取服务器IP、掩码和接口对应关系
    def ipGet(self):
        (status, output) = commands.getstatusoutput("ip a")
        patt_netip = re.findall(
            r'inet\s(?P<ip>\d+\.\d+\.\d+\.\d+)\/(?P<netmask>\d+).+?global\s(?P<card>.+)',
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
                return {'errcode':2, 'errmsg': 'ERROR_IP_FORMAT'}
            # 网关地址与IP重复
            elif self.gwip == i['ip']:
                return {'errcode': 3, 'errmsg': 'IP_GETWAY_EQUAL'}
            # 网关地址与IP在相同子网
            elif ip['nid']['dotted_decimal'] == gw['nid']['dotted_decimal']:
                ifinfo['ip'] = i['ip']
                ifinfo['nid'] = ip['nid']['dotted_decimal']
                ifinfo['netmask'] = i['netmask']
                ifinfo['gw'] = self.gwip
                ifinfo['if'] = i['if']
                ifinfo['errcode'] = 0
                return ifinfo
        return {'errcode': 5, 'errmsg': 'IP_GW_NOT_IN_SAME_NETWORK'}

# 路由脚本生成部分，后面会用定义个函数专门执行脚本

    # 这里使用type来控制删除还是添加路由操作
    # 为每张路由表生成默认路由和直连路由
    def setRouter(self, table, type):
        if_match = self.ifMatch()
        if if_match['errcode']:
            return if_match
        ispname, routelist = self.ispname, []
        nid, netmask, interface, gw = if_match['nid'], if_match['netmask'], if_match['if'], if_match['gw']
        # 删除路由表中的直连和默认路由
        # 这里测试删除再添加，PING并无丢包，延时有2ms的增加。
        if type == 'update':
            route = 'ip route flush table {}'.format(ISP_TABLE[ispname])
            routelist.append(route)
        # 为路由表添加直连路由
        route = 'ip route add to {}/{} dev {} table {}'.format(nid, netmask, interface, ISP_TABLE[ispname])
        routelist.append(route)
        # 添加默认路由
        route = 'ip route add default via {} dev {} table {}'.format(gw, interface, ISP_TABLE[ispname])
        routelist.append(route)
        return {'errcode': 0, 'routelist': routelist}


class RequireRule(object):
    def __init__(self, ispname):
        super(RequireRule, self).__init__()
        self.ispname = str(ispname)

# rule脚本生成部分，后面会用定义个函数专门执行脚本

    # 查看/tmp/下有没有对应ISP目的IP段的列表文件，没有就起git上下载
    def getRule(self):
        if not os.path.exists(rule_file[self.ispname]):
            try:
                log('', 'Download rule list from {}'.format(rule_URL[self.ispname]))
                r = requests.get(rule_URL[self.ispname], timeout=3)
            except requests.exceptions.ConnectionError:
                return {'errcode': 4, 'errmsg': 'ISP_URL_CONNECT_TIMEOUT'}
            # r = requests.get(rule_URL[self.ispname], timeout=3)
            segment = r.content.split('\n')
            return {'errcode': 0, 'segment': segment}
        else:
            log('', 'Use rule list from {}'.format(rule_file[self.ispname]))
            with open(rule_file[self.ispname], "r") as f:
                segment = f.readlines()
            return {'errcode': 0, 'segment': segment}

    # 为明细路由生成rule条目脚本，后面再用executeScript()脚本执行
    def setRuler(self):
        # 这个地方没做下载成功判断
        segment = self.getRule()
        if not segment['errcode']:
            segment = segment['segment']
        else:
            return segment
        rulelist = []
        # 将全局优先级变量传进来
        normal_start_pref, normal_end_pref = ISP_PREF[self.ispname]['start'], ISP_PREF[self.ispname]['end']
        update_start_pref, update_end_pref = ISP_PREF[self.ispname]['start'] + 10000, ISP_PREF[self.ispname]['end'] + 10000
        # 这里添加rule的构思是先将新策略添加到11001-20000策略中
        for seg in segment:
            # 支持在ISP网段列表含有#号的行均为备注，空行不关注
            if '#' in seg or seg == '': continue
            # 去掉segment里面的回车，这个地方用了三个replace，不知道需不需要优化
            seg = seg.replace('\n', '').replace('\r\n', '').replace('\r', '')
            rulelist.append('ip rule add to {} table {} pref {}'.format(seg, ISP_TABLE[self.ispname], update_start_pref))
            update_start_pref += 1

        # 再删除原先1001-10000的旧策略，如果修改定义范围一定要修改此处！！！！！！！
        for pref in range (normal_start_pref, normal_end_pref + 1):
            rulelist.append('ip rule del pref {}'.format(pref))

        # 再把新策略添加一次到1001-10000
        normal_start_pref, normal_end_pref = ISP_PREF[self.ispname]['start'], ISP_PREF[self.ispname]['end']
        for seg in segment:
            # 支持在ISP网段列表含有#号的行均为备注，空行不关注
            if '#' in seg or seg == '': continue
            # 去掉segment里面的回车，这个地方用了三个replace，不知道需不需要优化
            seg = seg.replace('\n', '').replace('\r\n', '').replace('\r', '')
            rulelist.append('ip rule add to {} table {} pref {}'.format(seg, ISP_TABLE[self.ispname], normal_start_pref))
            normal_start_pref += 1

        # 再删除11001-20000策略中的新策略，这个地方update_start_pref前面有自加的情况，所以重新赋值
        update_start_pref, update_end_pref = ISP_PREF[self.ispname]['start'] + 10000, ISP_PREF[self.ispname]['end'] + 10000
        for pref in range (update_start_pref, update_end_pref + 1):
            rulelist.append('ip rule del pref {}'.format(pref))

        return {'errcode': 0, 'rulelist': rulelist}

    # 这里补一个初始化清空rule表的方法，直接执行，不生成脚本
    def resetRuler(self):
        for pref in range (1, 32766):
            rule = 'ip rule del pref {}'.format(pref)
            (status, output) = commands.getstatusoutput(rule)
            rate('Reset rule', pref, 32766)
        print ('Reset rule progress has been completed.')


# 上面的方法都是生成脚本，最后统一在该方法调用系统命令执行
def executeScript(progressname, command):
    for i, route in enumerate(command):
        (status, output) = commands.getstatusoutput(route)
        rate(progressname, i, len(command))
        # 这个地方缺对shell命令执行的报错处理、和执行进度的处理。
        if status and status != 65024:
            log('{} line'.format(i + 1), output)

# 需不需要写一个专门生成日志的方法
def log(errcode, errmsg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    log = "Time: {} {} {}".format(timestamp, errcode, errmsg)
    print log
    logfile = open(LOGFILE, 'a+')
    logfile.write(log + '\n')

# 这是一个提供命令执行进度百分百的方法
def rate(progressname, current, total):
    if total < 100:
        total = total * 100
        current = current * 100
    threshold = total / 100
    if current % threshold == 0:
        percent = lambda x: x / threshold if x / threshold < 100 else 100
        sys.stdout.write('{} has started, completed {}%...\r'.format(progressname, percent(current)))
        sys.stdout.flush()

# 路由配置
def router(**kwargs):
    for ispname, gwip in kwargs['ISP'].items():
        if gwip:
            pbr = RequireRoute(ispname, gwip)
            # 这里控制是否先删除路由
            type = 'update' if kwargs['update'] else 'add'
            # 先生成路由脚本
            sys.stdout.write('Generating script operations.\r')
            sys.stdout.flush()
            route = pbr.setRouter(ispname, type)
            if not route['errcode']:
                executeScript('Set {} route to {}'.format(ispname, gwip), route['routelist'])
                log('', 'Set {} route to {} progress has been completed.').format(ispname, gwip)
            else:
                errmsg = 'ispname: {} gwip: {} errmsg: {}'.format(ispname, gwip, route['errmsg'])
                errcode = 'errcode: {}'.format(route['errcode'])
                log(errcode, errmsg)
# 策略配置
def ruler(**kwargs):
    # 清除rule表
    if kwargs['remove']:
        pbr = RequireRule('')
        pbr.resetRuler()
    # 选择更新某个表，或者更新三张表
    elif kwargs['update']:
        for ispname, judge in kwargs['ISP'].items():
            if judge:
                pbr = RequireRule(ispname)
                sys.stdout.write('Generating script operations.\r')
                sys.stdout.flush()
                rule = pbr.setRuler()
                if not rule['errcode']:
                    executeScript('Set {} rule'.format(ispname), rule['rulelist'])
                    log('', 'Set {} rule progress has been completed.'.format(ispname))
                else:
                    errmsg = 'ispname: {} errmsg: {}'.format(ispname, rule['errmsg'])
                    errcode = 'errcode: {}'.format(rule['errcode'])
                    log(errcode, errmsg)

def main():
    args = docopt(__doc__, version='Policy Based Routing for Linux 1.0')
    if args['route']:
        kwargs = {
            'ISP': {'CMB': args['--cmb-gw'],
                    'CTL': args['--ctl-gw'],
                    'CUC': args['--cuc-gw'],
                    },
            'add': args['add'],
            'update': args['update'],
        }
        router(**kwargs)
    elif args['rule']:
        kwargs = {
            'ISP': {'CMB': args['cmb'],
                   'CTL': args['ctl'],
                   'CUC': args['cuc'],
                   },
            'remove': args['remove'],
            'update': args['update'],
        }
        ruler(**kwargs)

if __name__ == '__main__':
    main()
