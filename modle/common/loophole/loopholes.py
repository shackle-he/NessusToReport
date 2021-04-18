#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# ------------------------------------------------------------
# File: loopholes.py
# Created Date: 2020/6/24
# Created Time: 0:15
# Author: Hypdncy
# Author Mail: hypdncy@outlook.com
# Copyright (c) 2020 Hypdncy
# ------------------------------------------------------------
#                       .::::.
#                     .::::::::.
#                    :::::::::::
#                 ..:::::::::::'
#              '::::::::::::'
#                .::::::::::
#           '::::::::::::::..
#                ..::::::::::::.
#              ``::::::::::::::::
#               ::::``:::::::::'        .:::.
#              ::::'   ':::::'       .::::::::.
#            .::::'      ::::     .:::::::'::::.
#           .:::'       :::::  .:::::::::' ':::::.
#          .::'        :::::.:::::::::'      ':::::.
#         .::'         ::::::::::::::'         ``::::.
#     ...:::           ::::::::::::'              ``::.
#    ````':.          ':::::::::'                  ::::..
#                       '.:::::'                    ':'````..
# ------------------------------------------------------------
import logging
import re
import json
import csv
import sqlite3
from pathlib import Path
from collections import OrderedDict

from modle.common.loophole.base import LoopholesBase

from cnf.const import json_loops_error, json_loops_global, risk_scores, risk_en2cn, vuln_db_info, vuln_db_file, \
    vuln_info, risk_range_en, nessus_csv_dir, nessus_csv_order
from config import nessus_vuln_self, nessus_risk_self, nessus_ignore_ids
from cnf.data import host_loop_ports, loop_host_ports


class Loopholes(LoopholesBase):
    """
    定义主机漏洞类
    """

    def __init__(self):
        """
        初始化文件
        :param plugin_id:
        """
        super(Loopholes, self).__init__()
        self.loops_global = OrderedDict()
        self.loops_error = OrderedDict()

    def _get_init_nessus(self):
        """
        :return:
        """

        p = Path(nessus_csv_dir)
        nessus_csvs = p.glob("*.csv")
        for file in nessus_csvs:
            with open(str(file), "r", encoding="ISO-8859-1") as f:
                next(f)
                rows = csv.reader(f)
                for row in rows:
                    host = str(row[nessus_csv_order["host"]])
                    plugin_id = str(row[nessus_csv_order["plugin_id"]])
                    if not (plugin_id in nessus_vuln_self or row[nessus_csv_order["risk_en"]] in risk_range_en):
                        continue

                    port = str(row[nessus_csv_order["port"]])
                    info = vuln_info.copy()
                    for key in vuln_info.copy():
                        info[key] = re.sub(r"\s+", " ", row[nessus_csv_order[key]]) if key in nessus_csv_order else ""
                    info["risk_cn"] = risk_en2cn[info["risk_en"]]
                    self.loops_global.setdefault(plugin_id, info)

                    loop_host_ports.setdefault(plugin_id, dict()).setdefault(host, set([])).add(port)
                    host_loop_ports.setdefault(host, dict()).setdefault(plugin_id, set([])).add(port)

    def _is_loop(self, row):
        res = 0
        plugin_id = str(row[nessus_csv_order["plugin_id"]])
        if plugin_id in nessus_ignore_ids:
            pass
        elif plugin_id in nessus_vuln_self or row[nessus_csv_order["risk_en"]] in risk_range_en:
            res = 1
        return res

    def update_db_loops(self):
        conn = sqlite3.connect(vuln_db_file)
        c = conn.cursor()
        for plugin_id, info in self.loops_global.items():
            rows = c.execute(
                "select * from {table} WHERE plugin_id = '{plugin_id}';".format(table=vuln_db_info["vuln_table"],
                                                                                plugin_id=int(plugin_id)))

            for row in rows:
                for key, value in vuln_db_info["order"].items():
                    info[key] = str(row[value])
                break
            else:
                self.loops_error[plugin_id] = info
        conn.close()

    def update_self_loops(self):
        """
        更新自定义漏洞信息
        :return:
        """
        for plugin_id, info in nessus_vuln_self.items():
            self.loops_global.get(plugin_id, dict()).update(info)

    def sort_by_risk(self):
        self.loops_global = OrderedDict(
            sorted(self.loops_global.items(), key=lambda x: risk_scores[x[1]["risk_en"]], reverse=True))

    def update_self_levels(self):
        """
        更新自定义等级
        :return:
        """
        for risk_en, plugin_ids in nessus_risk_self.items():
            for plugin_id in plugin_ids:
                self.loops_global.get(plugin_id, dict()).update({"risk_en": risk_en, "risk_cn": risk_en2cn[risk_en]})

    def _post_vuln_web(self, info):
        """
        上报数据到服务器
        :return:
        """
        pass

    def _dump_loops(self):
        """
        序列化Error
        :return:
        """
        with open(json_loops_error, "w", encoding="UTF-8") as f:
            json.dump(self.loops_error, f, ensure_ascii=False, indent=4)

        for plugin_id in self.loops_error:
            self.loops_error[plugin_id] = self.loops_global[plugin_id]

        with open(json_loops_global, "w", encoding="UTF-8") as f:
            json.dump(self.loops_global, f, ensure_ascii=False, indent=4)

    def run(self):
        self._get_init_nessus()

        self.update_db_loops()
        self.update_self_loops()
        self.update_self_levels()

        self.sort_by_risk()
        logging.info("----漏洞种类总数：{0}".format(len(loop_host_ports)))
        logging.info("----漏洞主机总数：{0}".format(len(host_loop_ports)))
