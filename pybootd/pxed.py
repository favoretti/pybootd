# -*- coding: utf-8 -*-
#
# Copyright (c) 2010-2011 Emmanuel Blot <emmanuel.blot@free.fr>
# Copyright (c) 2010-2011 Neotion
# Copyright (c) 2012-2013 Vladimir Lazarenko <favoretti@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import re
import select
import socket
import string
import struct
import sys
import time
import pybootdconfig
from binascii import hexlify
from pybootd import PRODUCT_NAME
from util import hexline, to_bool, iptoint, inttoip, get_iface_config

BOOTP_PORT_REQUEST = pybootdconfig.BOOTP_PORT
BOOTP_PORT_REPLY = 68

BOOTREQUEST = 1
BOOTREPLY = 2

BOOTPFormat = '!4bIHH4s4s4s4s16s64s128s64s'
BOOTPFormatSize = struct.calcsize(BOOTPFormat)
DHCPFormat = '!4bIHH4s4s4s4s16s64s128s4s'
DHCPFormatSize = struct.calcsize(DHCPFormat)

(BOOTP_OP,BOOTP_HTYPE,BOOTP_HLEN,BOOTP_HOPS,BOOTP_XID,BOOTP_SECS,
 BOOTP_FLAGS,BOOTP_CIADDR,BOOTP_YIADDR,BOOTP_SIADDR,BOOTP_GIADDR,
 BOOTP_CHADDR,BOOTP_SNAME,BOOTP_FILE,BOOTP_VEND) = range(15)

BOOTP_FLAGS_NONE = 0
BOOTP_FLAGS_BROADCAST = 1<<15

COOKIE='\0x63\0x82\0x53\0x63'

DHCP_OPTIONS = {  0: 'Byte padding',
                  1: 'Subnet mask',
                  2: 'Time offset',
                  3: 'Routers',
                  4: 'Time servers',
                  5: 'Name servers',
                  6: 'Domain name servers',
                  7: 'Log servers',
                  8: 'Cookie servers',
                  9: 'Line printer servers',
                 10: 'Impress servers',
                 11: 'Resource location servers',
                 12: 'Host Name', # + PXE extensions
                 13: 'Boot file size',
                 14: 'Dump file',
                 15: 'Domain name',
                 16: 'Swap server',
                 17: 'Root path',
                 18: 'Extensions path',
                 # --- IP layer / host ---
                 19: 'IP forwarding',
                 20: 'Source routing',
                 21: 'Policy filter',
                 22: 'Maximum datagram reassembly size',
                 23: 'Default IP TTL',
                 24: 'Path MTU aging timeout',
                 25: 'Path MTU plateau table',
                 # --- IP Layer / interface ---
                 26: 'Interface MTU',
                 27: 'All subnets local',
                 28: 'Broadcast address',
                 29: 'Perform mask discovery',
                 30: 'Mask supplier',
                 31: 'Perform router discovery',
                 32: 'Router solicitation address',
                 33: 'Static route',
                 # --- Link layer ---
                 34: 'Trailer encapsulation',
                 35: 'ARP cache timeout',
                 36: 'Ethernet encaspulation',
                 # --- TCP ---
                 37: 'TCP default TTL',
                 38: 'TCP keepalive interval',
                 39: 'TCP keepalive garbage',
                 # --- Application & Services ---
                 40: 'Network Information Service domain',
                 41: 'Network Information servers',
                 42: 'Network Time Protocol servers',
                 43: 'Vendor specific',
                 44: 'NetBIOS over TCP/IP name server',
                 45: 'NetBIOS over TCP/IP datagram server',
                 46: 'NetBIOS over TCP/IP node type',
                 47: 'NetBIOS over TCP/IP scope',
                 48: 'X Window system font server',
                 49: 'X Window system display manager',
                 50: 'Requested IP address',
                 51: 'IP address lease time',
                 52: 'Option overload',
                 53: 'DHCP message',
                 54: 'Server ID',
                 55: 'Param request list',
                 56: 'Error message',
                 57: 'Message length',
                 58: 'Renewal time',
                 59: 'Rebinding time',
                 60: 'Class ID',
                 61: 'GUID',
                 64: 'Network Information Service+ domain',
                 65: 'Network Information Service+ servers',
                 66: 'TFTP server name',
                 67: 'Bootfile name',
                 68: 'Mobile IP home agent',
                 69: 'Simple Mail Transport Protocol servers',
                 70: 'Post Office Protocol servers',
                 71: 'Network News Transport Protocol servers',
                 72: 'World Wide Web servers',
                 73: 'Finger servers',
                 74: 'Internet Relay Chat server',
                 77: 'User Class',
                 93: 'System architecture',
                 94: 'Network type',
                 97: 'UUID',
                 175: 'iPXE encap opts',
                 255: 'End of DHCP options' }

DHCP_DISCOVER = 1
DHCP_OFFER = 2
DHCP_REQUEST = 3
DHCP_DECLINE = 4
DHCP_ACK = 5
DHCP_NAK = 6
DHCP_RELEASE = 7
DHCP_INFORM = 8
DHCP_RENEWING = 100

DHCP_IP_MASK = 1
DHCP_IP_GATEWAY = 3
DHCP_IP_DNS = 6
DHCP_LEASE_TIME = 51
DHCP_MSG = 53
DHCP_SERVER = 54
DHCP_END = 255

PXE_DISCOVERY_CONTROL = 6
DISCOVERY_MCAST_ADDR = 7
PXE_BOOT_SERVERS = 8
PXE_BOOT_MENU = 9
PXE_MENU_PROMPT = 10


class BootpError(Exception):
    """Bootp error"""
    pass


class BootpServer:
    """BOOTP Server
       Implements bootstrap protocol"""

    ACCESS_LOCAL = ['uuid', 'mac'] # Access modes, defined locally
    ACCESS_REMOTE = ['http']       # Access modes, remotely retrieved
    (ST_IDLE, ST_PXE, ST_DHCP) = range(3) # Current state

    def __init__(self, logger, config):
        self.sock = []
        self.log = logger
        self.config = config
        self.uuidpool = {} # key MAC address value, value UUID value
        self.ippool = {} # key MAC address string, value assigned IP string
        self.filepool = {} # key IP string, value pathname
        self.states = {} # key MAC address string, value client state
        name_ = PRODUCT_NAME.split('-')
        name_[0] = 'bootp'
        self.netconfig = get_iface_config(self.config.get_bootp_bind_interface())
        if not self.netconfig:
            raise BootpError('Unable to detect network configuration')
        keys = sorted(self.netconfig.keys())
        self.log.info('Using %s' % ', '.join(map(':'.join,
                                zip(keys, [self.netconfig[k] for k in keys]))))
        access = self.config.get_bootp_acl_type()
        if not access:
            self.acl = None
        else:
            access = access.lower()
            if access not in self.ACCESS_LOCAL + self.ACCESS_REMOTE:
                raise BootpError('Invalid access mode: %s' % access)
            if not self.config.has_section(access):
                raise BootpError("Missing access section '%s'" % access)
            self.acl = {}
            if access in self.ACCESS_LOCAL:
                for entry in self.config.options(access):
                    self.acl[entry.upper()] = \
                        to_bool(self.config.get(access, entry))
        self.access = access

    # Public
    def get_netconfig(self):
        return self.netconfig

    def bind(self):
        host = self.netconfig['address']
        port = self.config.get_bootp_port()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                             socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.append(sock)
        self.log.info('Listening to %s:%s' % (host, port))
        sock.bind((host, int(port)))

    def forever(self):
        while True:
            try:
                r,w,e = select.select(self.sock, [], self.sock)
                for sock in r:
                    data, addr = sock.recvfrom(556)
                    self.handle(sock, addr, data)
            except Exception, e:
                import traceback
                self.log.critical('%s\n%s' % (str(e), traceback.format_exc()))
                time.sleep(1)

    def parse_options(self, tail):
        self.log.debug('Parsing DHCP options')
        dhcp_tags = {}
        while tail:
            tag = ord(tail[0])
            # padding
            if tag == 0:
                continue
            if tag == 0xff:
                return dhcp_tags
            length = ord(tail[1])
            (value, ) = struct.unpack('!%ss' % length, tail[2:2+length])
            tail = tail[2+length:]
            try:
                option = DHCP_OPTIONS[tag]
                self.log.debug(" option %d: '%s', size:%d %s" % \
                               (tag, option, length, hexline(value)))
            except KeyError:
                self.log.error('  unknown option %d, size:%d %s:' % \
                                (tag, length, hexline(value)))
                return None
            dhcp_tags[tag] = value

    def build_pxe_options(self, options, server):
        try:
            buf = ''
            uuid = options[97]
            buf += struct.pack('!BB%ds' % len(uuid),
                               97, len(uuid), uuid)
            clientclass = options[60]
            clientclass = clientclass[:clientclass.find(':')]
            buf += struct.pack('!BB%ds' % len(clientclass),
                               60, len(clientclass), clientclass)
            vendor = ''
            vendor += struct.pack('!BBB', PXE_DISCOVERY_CONTROL, 1, 0x0A)
            vendor += struct.pack('!BBHB4s', PXE_BOOT_SERVERS, 2+1+4,
                                  0, 1, server)
            srvstr = 'Python'
            vendor += struct.pack('!BBHB%ds' % len(srvstr), PXE_BOOT_MENU,
                                  2+1+len(srvstr), 0, len(srvstr), srvstr)
            prompt = 'Stupid PXE'
            vendor += struct.pack('!BBB%ds' % len(prompt), PXE_MENU_PROMPT,
                                  1+len(prompt), len(prompt), prompt)
            buf += struct.pack('!BB%ds' % len(vendor), 43,
                               len(vendor), vendor)
            buf += struct.pack('!BBB', 255, 0, 0)
            return buf
        except KeyError, e:
            self.log.error('Missing options, cancelling: ' + str(e))
            return None

    def build_dhcp_options(self, clientname):
        buf = ''
        if not clientname:
            return buf
        buf += struct.pack('!BB%ds' % len(clientname),
                           12, len(clientname), clientname)
        return buf

    def handle(self, sock, addr, data):
        sender = addr
        self.log.info('Sender: %s on socket %s' % (addr, sock.getsockname()))
        if len(data) < DHCPFormatSize:
            self.log.error('Cannot be a DHCP or BOOTP request - too small!')
        tail = data[DHCPFormatSize:]
        buf = list(struct.unpack(DHCPFormat, data[:DHCPFormatSize]))
        if buf[BOOTP_OP] != BOOTREQUEST:
            self.log.warn('Not a BOOTREQUEST')
            return
        options = self.parse_options(tail)
        if options is None:
            self.log.warn('Error in option parsing, ignore request')
            return

        # Extras (DHCP options)
        try:
            dhcp_msg_type = ord(options[53][0])
        except KeyError:
            dhcp_msg_type = None

        server_addr = self.netconfig['address']
        mac_addr = buf[BOOTP_CHADDR][:6]
        gi_addr = buf[BOOTP_GIADDR][:4]
        mac_str = ':'.join(['%02X' % ord(x) for x in mac_addr])
        gi_str = '.'.join(['%d' % ord(x) for x in gi_addr])
        self.log.debug("Gateway address: %s" % gi_str)
        # is the UUID received (PXE mode)
        if 97 in options and len(options[97]) == 17:
            uuid = options[97][1:]
            pxe = True
            self.log.info('PXE UUID has been received')
        # or retrieved from the cache (DHCP mode)
        else:
            uuid = self.uuidpool.get(mac_addr, None)
            pxe = False
            self.log.info('PXE UUID not present in request')
        uuid_str = uuid and ('%s-%s-%s-%s-%s' % \
            tuple([hexlify(x) for x in uuid[0:4], uuid[4:6], uuid[6:8],
                                       uuid[8:10], uuid[10:16]])).upper()
        if uuid_str:
            self.log.info('UUID is %s for MAC %s' % (uuid_str, mac_str))

        hostname = ''
        filename = ''

        # Basic state machine
        currentstate = self.states.setdefault(mac_str, self.ST_IDLE)
        newstate = currentstate
        if currentstate == self.ST_IDLE:
            if pxe and (dhcp_msg_type == DHCP_DISCOVER):
                # BIOS is booting up, and try to locate a DHCP server
                newstate = self.ST_PXE
        elif currentstate == self.ST_PXE:
            if not pxe and (dhcp_msg_type == DHCP_REQUEST):
                # OS is booting up, and confirm a previous DHCP dicovery
                newstate = self.ST_DHCP
        else: # currentstate == self.ST_DHCP
            if pxe:
                # OS was running but the BIOS is performing a DHCP request:
                # board has been restarted
                newstate = self.ST_PXE

        # if the state has not evolved from idle, there is nothing to do
        if newstate == self.ST_IDLE:
            self.log.info('Request from %s ignored (idle state)' % mac_str)
            sdhcp = self.config.get_bootp_allow_simple_dhcp()
            simple_dhcp = sdhcp and to_bool(sdhcp)
            if not simple_dhcp:
               return

        # construct reply
        buf[BOOTP_OP] = BOOTREPLY
        self.log.info('Client IP: %s' % socket.inet_ntoa(buf[7]))
        if buf[BOOTP_CIADDR] == '\x00\x00\x00\x00':
            self.log.debug('Client needs its address')
            host_data = self.get_host_data_for_mac(mac_str)
            ipaddr = host_data['address']

            self.log.debug("IPADDR: {0}".format(ipaddr))
            if not ipaddr:
                self.log.error("Can't get IP address!")
                return
            ip = None
            if mac_str in self.ippool:
                ip = self.ippool[mac_str]
                self.log.info('Lease for MAC %s already defined as IP %s' % \
                                (mac_str, ip))
            else:
                self.ippool[mac_str] = ipaddr
                ip = ipaddr

            if not ip:
                #raise BootpError('No more IP available in definined pool')
                self.log.error("Can not find IP assigned to mac: %s" % mac_str)
                return

            mask = iptoint(self.netconfig['mask'])
            reply_broadcast = iptoint(ip) & mask
            reply_broadcast |= (~mask)&((1<<32)-1)
            buf[BOOTP_YIADDR] = socket.inet_aton(ip)
            buf[BOOTP_SECS] = 0
            buf[BOOTP_FLAGS] = BOOTP_FLAGS_NONE
            addr = (inttoip(reply_broadcast), addr[1])
            self.log.debug('Reply to: %s:%s' % addr)
        else:
            buf[BOOTP_YIADDR] = buf[BOOTP_CIADDR]
            ip = socket.inet_ntoa(buf[BOOTP_YIADDR])
        buf[BOOTP_SIADDR] = socket.inet_aton(server_addr)
        if gi_addr:
            self.log.debug('Reply via gateway: %s' % gi_str)
            buf[BOOTP_GIADDR] = socket.inet_aton(gi_str)
        # sname
        buf[BOOTP_SNAME] = \
            '.'.join([host_data['hostname'], host_data['domain']])
        # file
        buf[BOOTP_FILE] = 'boot_file' in host_data and host_data['boot_file'] or self.config.get_bootp_default_boot_file()

        if not dhcp_msg_type:
            self.log.warn('No DHCP message type found, discarding request')
            return
        if dhcp_msg_type == DHCP_DISCOVER:
            self.log.debug('DHCP DISCOVER')
            dhcp_reply = DHCP_OFFER
            self.log.info('Offering lease for MAC %s: IP %s' % \
                          (mac_str, ip))
        elif dhcp_msg_type == DHCP_REQUEST:
            self.log.debug('DHCP REQUEST')
            dhcp_reply = DHCP_ACK
            self.log.info('New lease for MAC %s: IP %s' % \
                          (mac_str, ip))
        elif dhcp_msg_type == DHCP_RELEASE:
            self.log.info('DHCP RELEASE')
            if not self.notify:
                return
        elif dhcp_msg_type == DHCP_INFORM:
            self.log.info('DHCP INFORM')
            return
        elif dhcp_msg_type == DHCP_DECLINE:
            self.log.debug('DHCP DECLINE')
            return
        else:
            self.log.error('Unmanaged DHCP message: %d' % dhcp_msg_type)
            return

        pkt = struct.pack(DHCPFormat, *buf)
        pkt += struct.pack('!BBB', DHCP_MSG, 1, dhcp_reply)
        #server = socket.inet_aton(server_addr)
        # FIXME: Hardcoded relay and netmask
        # Add something in lines of:
        # networks:
        #     10.40.13.160:
        #         netmask: 255.255.255.224
        #         gateway: 10.40.13.160
        #         dns: 10.40.1.80, 10.40.1.81
        server = socket.inet_aton('10.40.13.161')
        pkt += struct.pack('!BB4s', DHCP_SERVER, 4, server)
        #mask = socket.inet_aton(self.netconfig['mask'])
        mask = socket.inet_aton('255.255.255.224')
        pkt += struct.pack('!BB4s', DHCP_IP_MASK, 4, mask)
        pkt += struct.pack('!BB4s', DHCP_IP_GATEWAY, 4, server)
        # FIXME: Serving only default DNS for now
        dns = self.config.get_bootp_default_dns()

        if dns:
            if dns.lower() == 'auto':
                dns = self.get_dns_server() or socket.inet_ntoa(server)
            dns = socket.inet_aton(dns)
            pkt += struct.pack('!BB4s', DHCP_IP_DNS, 4, dns)
        pkt += struct.pack('!BBI', DHCP_LEASE_TIME, 4,
                           int(self.config.get_bootp_default_lease_time()))
        pkt += struct.pack('!BB', DHCP_END, 0)

        # do not attempt to produce a PXE-augmented response for
        # regular DHCP requests
        if pxe:
            extra_buf = self.build_pxe_options(options, server)
            if not extra_buf:
                return
        else:
            extra_buf = self.build_dhcp_options(hostname)

        # update the UUID cache
        if pxe:
            self.uuidpool[mac_addr] = uuid

        # send the response
        if gi_addr:
            sock.sendto(pkt + extra_buf, (gi_str, 67))
        else:
            sock.sendto(pkt + extra_buf, addr)

        # update the current state
        if currentstate != newstate:
            self.log.info('Moving from state %d to state %d' % \
                            (currentstate, newstate))
            self.states[mac_str] = newstate

    def get_dns_server(self):
        nscre = re.compile('nameserver\s+(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})\s')
        try:
            with open('/etc/resolv.conf', 'r') as resolv:
                for line in resolv:
                    mo = nscre.match(line)
                    if mo:
                        dns = mo.group(1)
                        self.log.info('Found primary nameserver: %s' % dns)
                        return dns
        except Exception, e:
            pass
        self.log.info('No nameserver found')
        return None

    def get_filename(self, ip):
        """Returns the filename defined for a host"""
        filename = self.filepool.get(ip, '')
        self.log.info("Filename for IP %s is '%s'" % (ip, filename))
        return filename

    def get_host_data_for_mac(self, mac_str):
        self.log.debug("Host data requested for MAC: %s" % mac_str)
        try:
            host_lease_data = self.config.get_lease_for_mac(mac_str)
            hostname = 'hostname' in host_lease_data and host_lease_data['hostname']
            if not hostname:
                self.log.error("No hostname defined for mac: {mac}".format(mac=mac_str))
                return

            self.log.debug("Will try to resolve: {host}".format(host=hostname))
            try:
                ipaddr = socket.gethostbyname(hostname)
            except Exception, e:
                self.log.debug("Resolving failed: {0}".format(e))
                return
            self.log.debug("Got IP for {host}: {ip}".format(ip=ipaddr, host=hostname))
            hostdata = {}
            hostdata['address'] = ipaddr
            hostdata['hostname'] = hostname
            hostdata['domain'] = ".".join(hostname.strip().split(".")[1:])
            hostdata['boot_file'] = host_lease_data['boot_file']
            print hostdata
            return hostdata
        except IOError, e:
            self.log.error("No file {dhcp_home}/{mac_str} found!".format(dhcp_home=self.dhcp_home, mac_str=mac_str))

