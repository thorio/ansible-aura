#!/usr/bin/python -tt
# -*- coding: utf-8 -*-


# Aura module mangled from the existing pacman.py
# This will only really deal with installation and upgrading; pacman can remove
# packages installed by Aura.
# Does not deal with abs tree operations either (since I don't use them).

# TODO: Restructure this, and look at other modules for better examples
# (apt, yum and homebrew are good examples).

# TODO: Make aura class
# We keep passing around aura_path and module when we don't need to.

DOCUMENTATION = '''
---
module: aura
short_description: Manage packages with I(aura)
description:
    - Manage packages with the I(aura) package manager, an AUR helper for Arch
      Linux and its variants.
version_added: "2.3"
author:
    - "Alexandre Carlton"
notes: []
requirements: []
options:
    name:
        description:
            - Name of the package to install, upgrade, or remove.
        required: false
        default: null
        aliases: [ 'pkg', 'package' ]

    state:
        description:
            - Desired state of the package. Use I(pacman) to remove packages.
        required: false
        default: "present"
        choices: ["present", "latest"]

    upgrade:
        description:
            - Whether or not to upgrade all AUR packages.
        required: false
        default: no
        choices: ["yes", "no"]

    delmakedeps:
        description:
            - Whether or not to uninstall build dependencies that are no longer
              required after installing the main package.
        required: false
        default: no
        choices: ["yes", "no"]
'''

EXAMPLES = '''
# Install package foo
- aura: name=foo state=present

# Upgrade package foo
- aura: name=foo state=latest

# Run the equivalent of "aura -Au" as a separate step
- aura: upgrade=yes

'''

import itertools
import os
import re
import shlex
import sys

ANSI_ESCAPE_PATTERN = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')

# import module snippets
from ansible.module_utils.basic import *

def main():
    module = AnsibleModule(
        argument_spec   = dict(
            name        = dict(aliases=['pkg', 'package'], type='list'),
            state       = dict(default='present', choices=['present', 'installed', 'latest']),
            upgrade     = dict(default=False, type='bool'),
            delmakedeps = dict(default=False, type='bool')
        ),
        required_one_of = [['name', 'upgrade']],
        supports_check_mode = True)

    aura_path = module.get_bin_path('aura', True)

    p = module.params

    # normalize the state parameter
    if p['state'] in ['present', 'installed']:
        p['state'] = 'present'

    if p['upgrade']:
        upgrade(module, aura_path)

    if p['name']:
        pkgs = p['name']

        if module.check_mode:
            check_packages(module, aura_path, pkgs, p['state'])

        if p['state'] in ['present', 'latest']:
            install_packages(module, aura_path, p['state'], p['delmakedeps'], pkgs)


def query_installation_info(module, aura_path, name):
    """Queries the local installation.
    
    :param module: Ansible Module
    :param str aura_path:
    :param str name: Package name
    :rtype: dict[str, str]
    """
    query_command = "%s --query --info %s" % (aura_path, name)
    rc, stdout, _ = module.run_command(query_command, check_rc=False)
    if rc == 0:
        return extract_info(stdout)
    return {}
    
def query_aura_info(module, aura_path, name):
    """Queries the AUR for the package.
    Returns an empty dict if package could not be found.
    
    :param module: Ansible Module
    :param str aura_path:
    :param str name: Package name
    :rtype: dict[str, str]
    """
    query_command = "%s --aursync --info %s" % (aura_path, name)
    _, stdout, _ = module.run_command(query_command, check_rc=False)

    if stdout.strip():
        return extract_info(stdout)
    return {}


def query_package(module, aura_path, name, state="present"):
    """Query the package status in both the local system and the AUR.

    Returns:
     - a boolean to indicate if the package is installed
     - a boolean to indicate if the package is up-to-date
     - a boolean to indicate whether online information was available"""

    local_info = query_installation_info(module, aura_path, name)
    aura_info = query_aura_info(module, aura_path, name)

    installed = local_info != dict()
    online_info_available = aura_info != dict()

    if online_info_available:
        if not installed:
            uptodate = False

    if installed:
        # Not installed
        return dict(installed=False,
                    uptodate=False,
                    online=(aura_info != dict()))

    if state == "present":
        lcmd = "%s -Qi %s" % (aura_path, name)
        lrc, lstdout, lstderr = module.run_command(lcmd, check_rc=False)
        if lrc != 0:
            # package is not installed locally
            return False, False, False

        # get the version installed locally (if any)
        lversion = get_version(lstdout)

        rcmd = "%s -Ai %s" % (aura_path, name)
        rrc, rstdout, rstderr = module.run_command(rcmd, check_rc=False)
        # get the version in the repository
        rversion = get_version(rstdout)

        if rrc == 0:
            # Return True to indicate that the package is installed locally, and the result of the version number comparison
            # to determine if the package is up-to-date.
            return True, (lversion == rversion), False

        # package is installed but cannot fetch remote Version. Last True stands for the error
        return True, True, True

def needs_installation(module, aura_path, name, state):
    '''Determines whether we need to install the package
    :param ansible.module_utils.basic.AnsibleModule: Ansible Module
    :param str aura_path:
    :param str name:
    :param str state:
    ''' 

    # First check that the package exists on the AUR
    aur_info = query_aura_info(module, aura_path, name)
    if not aur_info:
        module.fail_json(msg="No package '%s' found on AUR." % name)

    local_info = query_installation_info(module, aura_path, name)
    if not local_info:
        # If the package does not exist locally, then it needs installing
        # regardless of state
        return True

    local_version = local_info['Version']
    print(local_version)
    aur_version = aur_info['Version']
    print(aur_version)

    # if state is latest, check that the versions match, otherwise 
    # if state is not latest (must be present), then the package exists but we
    # don't need to upgrade it.
    return state == 'latest' and local_version != aur_version


def upgrade(module, aura_path):
    '''
    :param ansible.module_utils.basic.AnsibleModule module: Ansible module
    :param str aura_path: Path to aura binary
    '''

    upgrade_command = "%s -A --sysupgrade --noconfirm" % (aura_path)
    upgrade_command_dry = "%s -A --sysupgrade --dryrun" % (aura_path)
    rc, stdout, stderr = module.run_command(upgrade_command_dry,
                                            check_rc=False)

    # So: 0 return on packages to upgrade, 1 if there is nothing to upgrade
    if rc == 0:
        if module.check_mode:
            data = stdout.split('\n')
            packages = list(itertools.takewhile(
                lambda line: line != '',
                itertools.dropwhile(
                    lambda line: 'aura >>=' in line,
                    data)))
            module.exit_json(
                changed=True,
                msg="%s package(s) would be upgraded" % (len(packages)))
        rc, stdout, stderr = module.run_command(upgrade_command, check_rc=False)
        if rc == 0:
            module.exit_json(changed=True, msg='System upgraded')
        else:
            module.fail_json(msg="Could not upgrade")
    else:
        module.exit_json(changed=False, msg="No AUR packages to upgrade")


def install_packages(module, aura_path, state, delmakedeps, packages):
    '''
    :type state: str
    :type delmakedeps: bool
    :type packages: list[str]
    '''
    successful_installs = 0
    packages_to_install = (package
                           for package in packages
                           if needs_installation(module,
                                                 aura_path,
                                                 package,
                                                 state))
    for package in packages_to_install:
        params = '--aursync %s' % package
        
        if delmakedeps:
            params += ' --delmakedeps'

        # TODO: --needed will not install it if already present... Could use this?
        # If state == present, plug in '--needed', and record number of packges
        # that don't output 'The following packages are already installed'.
        # Kind of doing too much in one step, though.
        command = "%s %s --noconfirm" % (aura_path, params)
        rc, stdout, stderr = module.run_command(command, check_rc=False)

        if rc != 0:
            module.fail_json(msg="Failed to install package '%s'." % package)

        successful_installs += 1

    if successful_installs > 0:
        module.exit_json(changed=True, msg="Installed %s package(s)." % successful_installs)

    module.exit_json(changed=False, msg="All packages already installed.")


def check_packages(module, aura_path, packages, state):
    would_be_changed = []
    for package in packages:
        installed, updated, unknown = query_package(module, aura_path, package)
        if ((state in ["present", "latest"] and not installed) or
                (state == "absent" and installed) or
                (state == "latest" and not updated)):
            would_be_changed.append(package)
    if would_be_changed:
        if state == "absent":
            state = "removed"
        module.exit_json(changed=True, msg="%s package(s) would be %s" % (
            len(would_be_changed), state))
    else:
        module.exit_json(changed=False, msg="package(s) already %s" % state)


def get_version(output):
    """
    :type output: str 
    :rtype: str
    """
    return extract_info(output).get('Version')

def extract_info(info):
    """Retrieves values from either pacman or aura output and returns a
    dictionary equivalent.

    :param str info: the output from either 'pacman -Ai' or 'aura -Ai'
    :returns: A dictionary containing the information needed.
    :rtype: dict[str, str]
    """
    colourless_info = re.sub(ANSI_ESCAPE_PATTERN, '', info)
    lines = colourless_info.split('\n')
    info_dict = {}
    for line in lines:
        if line:
            key, value = line.split(':', 1)
            info_dict[key.strip()] = value.strip()
    return info_dict



if __name__ == "__main__":
    main()
