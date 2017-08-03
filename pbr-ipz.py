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

import sys, re, os, time
import urllib2
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

ISP_TABLE = {'CTL': 20,
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


mask_mod = {
    '1': '128.0.0.0', '9': '255.128.0.0',  '17': '255.255.128.0', '25': '255.255.255.128',
    '2': '192.0.0.0', '10': '255.192.0.0', '18': '255.255.192.0', '26': '255.255.255.192',
    '3': '224.0.0.0', '11': '225.224.0.0', '19': '255.255.224.0', '27': '255.255.255.224',
    '4': '240.0.0.0', '12': '255.240.0.0', '20': '255.255.240.0', '28': '255.255.255.240',
    '5': '248.0.0.0', '13': '255.248.0.0', '21': '255.255.248.0', '29': '255.255.255.248',
    '6': '225.0.0.0', '14': '255.252.0.0', '22': '255.255.252.0', '30': '255.255.255.252',
    '7': '254.0.0.0', '15': '255.254.0.0', '23': '255.255.254.0', '31': '255.255.255.254',
    '8': '255.0.0.0', '16': '255.255.0.0', '24': '255.255.255.0', '32': '255.255.255.255',
}


class RequireIpz(object):
    def __init__(self, ip, mask):
        super(RequireIpz, self).__init__()
        self.ip = str(ip)
        self.mask = str(mask)

    #ip输入格式检查
    def formatCheck(self):
        ip, mask = self.ip, self.mask
        formatCheck_dict = {'errcode': 1, 'errmsg': []}
        #点分十进制ip地址检查
        if re.match("^(([01]?[0-9]{1,2}|2[0-4][0-9]|25[0-5])(\.([01]?[0-9]{1,2}|2[0-4][0-9]|25[0-5])){3}|([0-9a-fA-F]{1,4}:)+:?([0-9a-fA-F]{1,4}:)*[0-9a-fA-F]{1,4})$", ip) == None:
            #二进制IP地址检查
            if re.match("[1|0]{32}", ip) == None:
                formatCheck_dict['errmsg'].append('ERROR_IP_FORMAT')
                formatCheck_dict['errcode'] = 2
        #子网掩码检查合法性
        if mask not in mask_mod:
            if mask not in mask_mod.values():
                formatCheck_dict['errmsg'].append('ERROR_NETMASK_FORMAT')
                formatCheck_dict['errcode'] = 3
        if formatCheck_dict['errmsg'] == []:
            formatCheck_dict['errcode'] = 0
        return formatCheck_dict

    #输入点分十进制或者二进制都能给出十进制和二进制的字典集合
    def formatChange(self, var, type='dotted_decimal'):
        var = str(var)
        var_formats_dict = {'bin': '', 'dotted_decimal': ''}
        if type == "dotted_decimal":
            var_bin = "".join([ bin(int(i)).split('b')[1].zfill(8) for i in var.split('.')])
            var_formats_dict['bin'] = var_bin
            var_formats_dict['dotted_decimal'] = var
        elif type == "bin":
            var_dotted_decimal = ".".join([ str(int(var[0:8], 2)), str(int(var[8:16], 2)), str(int(var[16:24], 2)) , str(int(var[24:32], 2)) ])
            var_formats_dict['bin'] = var
            var_formats_dict['dotted_decimal'] = var_dotted_decimal
        return var_formats_dict

    #反向子网掩码
    def renetmasker(self):
        ip, mask = self.ip, self.mask
        mask = self.maskStyle()
        renetmask_dict = {'renetmask':'', 'bin':''}
        renetmask_dict['bin'] = ''.join([ str(int(i, 2) ^ 1) for i in mask['bin'][:] ])
        renetmask_dict['renetmask'] = self.formatChange(renetmask_dict['bin'], type='bin')['dotted_decimal']
        return renetmask_dict


    #输出子网掩码数字和点分十进制格式，返回字典格式
    def maskStyle(self):
        ip, mask = self.ip, self.mask
        mask_dict = {'digital': '', 'dotted_decimal': '','bin':''}
        #数字/24格式输入，输出点分十进制和二进制
        if mask in mask_mod:
            mask_dict['digital'] = mask
            mask_dict['dotted_decimal'] = mask_mod[mask]
            mask_dict['bin'] = self.formatChange(mask_dict['dotted_decimal'])['bin']
        #点分十进制输入，输出数字/24和二进制
        elif mask in mask_mod.values():
            for key, value in mask_mod.items():
                if mask == value:
                    mask_dict['digital'] = key
                    mask_dict['dotted_decimal'] = mask
                    mask_dict['bin'] = self.formatChange(mask)['bin']
        return mask_dict

    #子网号计算
    def nider(self):
        ip, mask = self.ip, self.mask
        ip = self.formatChange(ip)
        netmask = self.maskStyle()
        nid = str( bin(int(ip['bin'], 2) & int(netmask['bin'], 2)).split('b')[1] ).zfill(32)
        nid_dict = self.formatChange(nid, type='bin')
        return nid_dict

    #广播号计算
    def brder(self):
        ip, mask = self.ip, self.mask
        nid = self.nider()
        renetmask = self.renetmasker()
        brd = bin( int(nid['bin'], 2) ^ int(renetmask['bin'], 2) ).split('b')[1].zfill(32)
        brd_dict = self.formatChange(brd, type='bin')
        return brd_dict

    #可用主机范围
    def iprange(self):
        ip, mask, nid, brd = self.ip, self.mask, self.nider(), self.brder()
        if mask == '32' or mask == '255.255.255.255':
            start_ip_dict = end_ip_dict = self.formatChange(ip)
        else:
            start_ip = bin(int(nid['bin'], 2) + 1).split('b')[1].zfill(32)
            end_ip = bin(int(brd['bin'], 2) - 1).split('b')[1].zfill(32)
            start_ip_dict = self.formatChange(start_ip, type='bin')
            end_ip_dict = self.formatChange(end_ip, type='bin')
        ip_range_dict = {'start_ip': start_ip_dict, 'end_ip': end_ip_dict}
        return ip_range_dict

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
            ip = ipz(i['ip'], i['netmask'])
            gw = ipz(self.gwip, i['netmask'])
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
        table = ISP_TABLE[ispname]
        nid, netmask, interface, gw = if_match['nid'], if_match['netmask'], if_match['if'], if_match['gw']
        # 删除路由表中的直连和默认路由
        # 这里测试删除再添加，PING并无丢包，延时有2ms的增加。
        if type == 'update':
            route = 'ip route flush table {0}'.format(table)
            routelist.append(route)
        # 为路由表添加直连路由
        route = 'ip route add to {0}/{1} dev {2} table {3}'.format(nid, netmask, interface, table)
        routelist.append(route)
        # 添加默认路由
        route = 'ip route add default via {0} dev {1} table {2}'.format(gw, interface, table)
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
                log('', 'Download rule list from {0}'.format(rule_URL[self.ispname]))
                r = urllib2.urlopen(rule_URL[self.ispname], timeout=3)
            except urllib2.URLError:
                return {'errcode': 4, 'errmsg': 'ISP_URL_CONNECT_TIMEOUT'}
            segment = r.read().split('\n')
            return {'errcode': 0, 'segment': segment}
        else:
            log('', 'Use rule list from {0}'.format(rule_file[self.ispname]))
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
            rulelist.append('ip rule add to {0} table {1} pref {2}'.format(seg, ISP_TABLE[self.ispname], update_start_pref))
            update_start_pref += 1

        # 再删除原先1001-10000的旧策略，如果修改定义范围一定要修改此处！！！！！！！
        for pref in range (normal_start_pref, normal_end_pref + 1):
            rulelist.append('ip rule del pref {0}'.format(pref))

        # 再把新策略添加一次到1001-10000
        normal_start_pref, normal_end_pref = ISP_PREF[self.ispname]['start'], ISP_PREF[self.ispname]['end']
        for seg in segment:
            # 支持在ISP网段列表含有#号的行均为备注，空行不关注
            if '#' in seg or seg == '': continue
            # 去掉segment里面的回车，这个地方用了三个replace，不知道需不需要优化
            seg = seg.replace('\n', '').replace('\r\n', '').replace('\r', '')
            rulelist.append('ip rule add to {0} table {1} pref {2}'.format(seg, ISP_TABLE[self.ispname], normal_start_pref))
            normal_start_pref += 1

        # 再删除11001-20000策略中的新策略，这个地方update_start_pref前面有自加的情况，所以重新赋值
        update_start_pref, update_end_pref = ISP_PREF[self.ispname]['start'] + 10000, ISP_PREF[self.ispname]['end'] + 10000
        for pref in range (update_start_pref, update_end_pref + 1):
            rulelist.append('ip rule del pref {0}'.format(pref))

        return {'errcode': 0, 'rulelist': rulelist}

    # 这里补一个初始化清空rule表的方法，直接执行，不生成脚本
    def resetRuler(self):
        for pref in range (1, 32766):
            rule = 'ip rule del pref {0}'.format(pref)
            (status, output) = commands.getstatusoutput(rule)
            rate('Reset rule', pref, 32766)
        log('', 'Reset rule progress has been completed.')

def ipz(ip, netmask):
    ipa = RequireIpz(ip, netmask)
    if not ipa.formatCheck()['errcode']:
        ip_range = ipa.iprange()
        nid = ipa.nider()
        brd = ipa.brder()
        ip = ipa.formatChange(ip)
        netmask = ipa.maskStyle()
        renetmask = ipa.renetmasker()
        ipinfo = {  'ip': ip,
                    'nid': nid,
                    'brd': brd,
                    'ip_range': ip_range,
                    'netmask': netmask,
                    'renetmask': renetmask,
                    'errcode': 0,
                   }
        return ipinfo
    else:
        ipinfo = { 'errcode': ipa.formatCheck()['errcode'],
                   'errmsg': ipa.formatCheck()['errmsg'],
                   }
        return ipinfo

# 上面的方法都是生成脚本，最后统一在该方法调用系统命令执行
def executeScript(progressname, command):
    for i, route in enumerate(command):
        (status, output) = commands.getstatusoutput(route)
        rate(progressname, i, len(command))
        # 这个地方缺对shell命令执行的报错处理、和执行进度的处理。
        if status and not 'No such file or directory' in output:
            log('{0} line'.format(i + 1), output)

# 需不需要写一个专门生成日志的方法
def log(errcode, errmsg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    log = "Time: {0} {1} {2}".format(timestamp, errcode, errmsg)
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
        sys.stdout.write('{0} has started, completed {1}%...\r'.format(progressname, percent(current)))
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
                executeScript('Set {0} route to {1}'.format(ispname, gwip), route['routelist'])
                log('', 'Set {0} route to {1} progress has been completed.'.format(ispname, gwip))
            else:
                errmsg = 'ispname: {0} gwip: {1} errmsg: {2}'.format(ispname, gwip, route['errmsg'])
                errcode = 'errcode: {0}'.format(route['errcode'])
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
                    executeScript('Set {0} rule'.format(ispname), rule['rulelist'])
                    log('', 'Set {0} rule progress has been completed.'.format(ispname))
                else:
                    errmsg = 'ispname: {0} errmsg: {1}'.format(ispname, rule['errmsg'])
                    errcode = 'errcode: {0}'.format(rule['errcode'])
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
