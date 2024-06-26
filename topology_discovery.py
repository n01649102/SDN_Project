#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types

from ryu.topology.api import get_switch, get_link, get_host
from ryu.lib import hub
import json
import os
import subprocess

class SimpleSwitch13(app_manager.RyuApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.topology_api_app = self
        hub.spawn(self.myfunction)

    def myfunction(self):
        self.logger.info('started new thread')
        hub.sleep(10)

        switch_list = get_switch(self.topology_api_app, None)
        self.switches = [switch.dp.id for switch in switch_list]

        links_list = get_link(self.topology_api_app, None)
        print ('links_list:', links_list)
        self.links = [{'src': link.src.dpid, 'dst': link.dst.dpid,
                      'port': link.src.port_no} for link in links_list]

        host_list = get_host(self.topology_api_app, None)
        self.hosts = [{'MAC': host.mac, 'dpid': host.port.dpid,
                      'port': host.port.port_no} for host in host_list]

        self.logger.info('*********Topology Information*************')
        self.logger.info('Switches %s', self.switches)
        self.logger.info('Links %s', self.links)
        self.logger.info('Hosts %s', self.hosts)

        # ----------------------- Store Topology information in a file ----------------------------

        topology_data = {'switches': self.switches,
                         'links': self.links, 'hosts': self.hosts}

        with open('topology_data.json', 'w') as file:

            json.dump(topology_data, file)

        self.logger.info("Topology info stored in file 'topology_data.json'"
                         )

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow entry
        #
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.  The bug has been fixed in OVS v2.1.0.

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                   ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(
        self,
        datapath,
        priority,
        match,
        actions,
        buffer_id=None,
        ):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = \
            [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath,
                                    buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath,
                                    priority=priority, match=match,
                                    instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):

        # If you hit this you might want to increase
        # the "miss_send_length" of your switch

        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug('packet truncated: only %s of %s bytes',
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:

            # ignore lldp packet

            return
        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info('packet in %s %s %s %s', dpid, src, dst,
                         in_port)

        # learn a mac address to avoid FLOOD next time.

        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst,
                                    eth_src=src)

            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out

            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions,
                              msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions,
                                  data=data)
        datapath.send_msg(out)

    def push_file_to_github():

    # Change directory to the logs folder

        logs_folder = \
            r'/home/student/Desktop/Project/Final_SDN_Project_Files'
        os.chdir(logs_folder)

# Initialize a Git repository

    subprocess.run('git init', shell=True)

# Add the file to the repository

    subprocess.run('git add topology_data.json', shell=True)

# Commit the changes

    subprocess.run('git commit -m "commit"', shell=True)

    subprocess.run('git branch -M main', shell=True)

    subprocess.run('git remote add origin https://github.com/n01649102/SDN_Project.git'
                   , shell=True)

# Add remote repository
    subprocess.run('git remote set-url origin https://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@github.com/n01649102/SDN_Project', shell=True)

# Push changes to GitHub, forcing it
    subprocess.run('git push origin main --force', shell=True)
