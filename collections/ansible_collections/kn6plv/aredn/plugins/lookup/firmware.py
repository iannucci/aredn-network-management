#! /usr/bin/python
# python 3 headers, required if submitting to Ansible
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import requests
import re
import hashlib
import os
import json
from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from distutils.version import LooseVersion

DOCUMENTATION = """
  lookup: firmware
  author: Tim Wilkinson KN6PLV <tim.j.wilkinson@gmail.com>
  version_added: "0.1"
  short_description: fetch AREDN firmware
  description:
    - This lookup fetch and cache AREDN firmware for specific device
      and version. It returns a filename containing the appropriate firmware.
  options:
    _terms:
      description: Firmware version specified by the keyword parameter 'version'.  Valid values are 'release', 'nightly', 'nightly-babel', and a specific version string.
      required: True
  notes:
    - Uses device facts as part of selecting the appropriate firmware.
"""

root = 'http://downloads.arednmesh.org/afs/www/'
firmware_dir = "/tmp/aredn-firmware/"

os.makedirs(firmware_dir, exist_ok=True)


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        if "kn6plv_debug" in variables:
            debug = variables["kn6plv_debug"]
        else:
            debug = False
        if debug:
            print("terms: ")
            print(terms)  # a list; can't concatenate it to a string
        self.set_options(var_options=variables, direct=kwargs)

        board = variables["ansible_board"]
        if not board:
            raise AnsibleError("no board")
        boardtype = variables["ansible_hardware_type"]
        if not boardtype:
            raise AnsibleError("no hardware type")

        if debug:
            print("board: " + board)
            print("boardtype: " + boardtype)

        # Board type naming inconsistencies
        if re.match(r"^cpe", boardtype):
            boardtype = boardtype = "tplink," + boardtype
        if re.match(r"^rocket-m-xw", boardtype):
            boardtype = boardtype = "ubnt-" + boardtype
        if boardtype == "qemu-standard-pc-i440fx-piix-1996":
            boardtype = "generic"

        ret = []
        for version in terms:
            # Look for cached versions to avoid network traffic
            filename = firmware_dir + ("aredn-" + version + "-" + board + "-" + boardtype + "-squashfs-sysupgrade.bin").replace("/", "-").replace(",", "-")
            if version == "release" or version == "nightly" or version == "nightly-babel" or not os.path.exists(filename):
                if re.match(r"^\d\.\d\.\d\.\d$", version) or version == "release" or version == "nightly" or version == "nightly-babel":
                    resp = requests.get(root + "config.js")
                    if debug:
                        print("Querying " + root + "config.js: ")
                        print(resp.text)

                    # resp.text is of the form 

                    # /* exported config */
                    # 
                    # var config = {
                    #   // Show help text for images
                    #   show_help: true,

                    #   // Path to where overview.json can be found
                    #   versions: {'20250530-5d37834d': 'data/20250530-5d37834d', '3.24.10.0': 
                    #              'data/3.24.10.0', '3.22.8.0': 'data/3.22.8.0', '3.22.12.0': 
                    #              'data/3.22.12.0', '3.22.6.0': 'data/3.22.6.0', '3.22.1.0': 
                    #              'data/3.22.1.0', '3.25.5.0': 'data/3.25.5.0', '3.25.5.1': 
                    #              'data/3.25.5.1', '3.25.2.0': 'data/3.25.2.0', '3.24.4.0': 
                    #              'data/3.24.4.0', '3.24.6.0': 'data/3.24.6.0', '3.23.8.0': 
                    #              'data/3.23.8.0', '3.23.4.0': 'data/3.23.4.0', '3.23.12.0': 
                    #              'data/3.23.12.0', 'babel-20250531-ad138fca': 'data/babel-20250531-ad138fca'},

                    #   // Pre-selected version (optional)
                    #   default_version: "3.25.5.1",

                    #   // Image download URL (optional)
                    #   image_url: "http://downloads.arednmesh.org/",

                    #   // Info link URL (optional)
                    #   info_url: "https://openwrt.org/start?do=search&id=toh&q={title} @toh",
                    # };

                    releases = []
                    if resp.status_code != 200:
                        raise AnsibleError("cannot not find versions")

                    versions_string = re.search('versions: ({.+}),', resp.text).group(1)
                    versions_dict = json.loads(versions_string.replace("\'", "\""))  # using json.loads requires double quotes
                    for key in versions_dict:
                        releases.append(key)

                    # releases should look like this:
                    #
                    # ['20250530-5d37834d', '3.24.10.0', '3.22.8.0', '3.22.12.0', 
                    #  '3.22.6.0', '3.22.1.0', '3.25.5.0', '3.25.5.1', '3.25.2.0', 
                    #   '3.24.4.0', '3.24.6.0', '3.23.8.0', '3.23.4.0', '3.23.12.0', 
                    #   'babel-20250531-ad138fca']

                    # for v in re.finditer(r'versions: ({.+}),', resp.text):
                    #     for m in re.finditer(r'\'(.+?)\': \'data/(.+?)\'', v.group(1)):
                    #         releases.append(m.group(1))
                    if len(releases) == 0:
                        raise AnsibleError("no releases")
                    # releases.sort(key=LooseVersion)
                    if debug:
                        print("releases (pre-sort):")
                        print(releases)
                    releases.sort()
                    # releases is now of the form
                    #
                    # ['20250530-5d37834d', '3.22.1.0', '3.22.12.0', '3.22.6.0', 
                    #  '3.22.8.0', '3.23.12.0', '3.23.4.0', '3.23.8.0', '3.24.10.0', 
                    #  '3.24.4.0', '3.24.6.0', '3.25.2.0', '3.25.5.0', '3.25.5.1', 
                    #  'babel-20250531-ad138fca']
                    if debug:
                        print("releases (post-sort):")
                        print(releases)
                    if version == "release":
                        version_id = releases[-2]  # was -1 before Babel was added
                    elif version == "nightly":
                        version_id = releases[0]  # with key=LooseVersion, this selects the wrong firmware
                    elif version == "nightly-babel":
                        version_id = releases[-1]
                    # This is the case when a specific version string is passed in
                    elif version in releases:
                        version_id = version
                        pass
                    else:
                        raise AnsibleError("version not found: %s" % version)
                    if debug:
                        print("version: " + version_id)
                else:
                    raise AnsibleError("unknown version: %s" % version)

                resp = requests.get(root + "data/" + version_id + "/overview.json")
                if resp.status_code != 200:
                    raise AnsibleError("cannot read firmware overviews: %s" % (root + "data/" + version_id + "/overview.json"))
                overview = resp.json()
                if debug:
                    print("Querying " + root + "data/" + version_id + "/overview.json: ")
                    print(resp.text)
                target = False
                firmware_url = False
                if debug:
                    print("Searching over profiles, looking for " + boardtype)
                for profile in overview["profiles"]:
                    if profile["id"] == boardtype:
                        if debug:
                            print("Found it")
                        target = overview["image_url"].replace("{target}", profile["target"])
                        resp = requests.get(root + "data/" + version_id + "/" + profile["target"] + "/" + profile["id"] + ".json")
                        if resp.status_code != 200:
                            raise AnsibleError("cannot read firmware profile: %s" % (root + "data/" + version_id + "/" + profile["target"] + "/" + profile["id"] + ".json"))
                        profile = resp.json()
                        for image in profile["images"]:
                            if image["type"] == "sysupgrade" or image["type"] == "nand-sysupgrade" or image["type"] == "combined":
                                firmware_url = target + "/" + image["name"]
                                firmware_sha = image["sha256"]
                                break
                        break
                if not firmware_url:
                    raise AnsibleError("firmware not found: " + boardtype)

                # Fetch and verify firmware
                resp = requests.get(firmware_url)
                if resp.status_code != 200:
                    raise AnsibleError("cannot download firmware")
                if hashlib.sha256(resp.content).hexdigest() != firmware_sha:
                    raise AnsibleError("firmware checksum failed")

                # Store content in a file
                f = open(filename, mode="w+b")
                f.write(resp.content)
                f.close()

            f = open(filename, mode="r+b")
            sha = hashlib.sha256(f.read()).hexdigest()
            f.close()

            ret.append({"version": version_id, "file": filename, "sha256": sha, "size": os.path.getsize(filename)})

        return ret
