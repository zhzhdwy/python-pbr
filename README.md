# pbr.py脚本根据 Owen wang 的route3.sh脚本进行编写，在这里也会把该脚本上传上来。
# 该功能主要为多线多IP服务器做策略路由，上层网络设备根据源地址做PBR，服务器上需要针对不同的目的IP配置路由策略。
# 根据公司需求，多线服务器使用rule表控制明细路由指到服务器中某个路由表中，路由表中再做路由控制。
# pbr.py该脚本需要docopt包做支持，在python2.x环境中使用，2.6和2.7做个测试，无不良反应。
# pip install -r requirements.txt