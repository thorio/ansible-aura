# Ansible module for Aura

Basic module that implements installations and upgrades using [Aura](https://github.com/aurapm/aura), an AUR helper for ArchLinux.

The following functionalities are implemented:

 - installation of a package 
 - upgrade of all AUR packages

To install this module, you can either:

 - download `aura.py` and place it in the `library` folder of your top-level playbook.
 - clone this as a submodule, adding the path to the `library` value your `ansible.cfg`.
