
from library import aura as aura_module
from utils import AnsibleExitJson, AnsibleFailJson, ModuleTestCase, set_module_args
from ansible.compat.tests.mock import patch, call

# test_parted is a pretty good start.

class TestAura(ModuleTestCase):

    def setUp(self):
        super(TestAura, self).setUp()
        self.module = aura_module

        self.mock_run_command = patch('ansible.module_utils.basic.AnsibleModule.run_command')
        self.run_command = self.mock_run_command.start()

        self.mock_get_bin_path = patch('ansible.module_utils.basic.AnsibleModule.get_bin_path')
        self.get_bin_path = self.mock_get_bin_path.start()
        self.get_bin_path.return_value = '/usr/bin/aura'

    def tearDown(self):
        self.mock_run_command.stop()
        self.mock_get_bin_path.stop()

    # This is what we actually call in our tests, setting our expectations
    # of what should happen.
    def execute_module(self, failed=False, changed=False):
        if failed:
            result = self.failed()
            self.assertTrue(result['failed'], result)
        else:
            result = self.changed(changed)
            self.assertEqual(result['changed'], changed, result)

        return result

    def failed(self):
        with self.assertRaises(AnsibleFailJson) as exc:
            self.module.main()

        result = exc.exception.args[0]
        self.assertTrue(result['failed'], result)
        return result

    def changed(self, changed=False):
        with self.assertRaises(AnsibleExitJson) as exc:
            self.module.main()

        result = exc.exception.args[0]
        self.assertEqual(result['changed'], changed, result)
        return result

    def set_side_effect(self, side_effect):
        self.run_command.side_effect = lambda *args, **kwargs: side_effect[args[0]]


    def test_install_already_present(self):
        set_module_args({
            'name': 'foo',
            'state': 'present',
        })
        self.set_side_effect({
            '/usr/bin/aura --query --info foo': (0, "Name : foo", None)
        })
        self.execute_module()

    def test_install_version_present_is_latest(self):
        set_module_args({
            'name': 'foo',
            'state': 'latest',
        })
        self.set_side_effect({
            '/usr/bin/aura --query --info foo': (0, "Version : 1", None),
            '/usr/bin/aura --aursync --info foo': (0, "Version  : 1", None),
        })
        self.execute_module()

    def test_install_newer_version_on_aur(self):
        set_module_args({
            'name': 'foo',
            'state': 'latest',
        })
        self.set_side_effect({
            '/usr/bin/aura --query --info foo': (0, "Version : 1", None),
            '/usr/bin/aura --aursync --info foo': (0, "Version  : 2", None),
            '/usr/bin/aura --aursync --builduser=nobody foo --noconfirm': (0, "Determining dependencies...", None)
        })
        self.execute_module(changed=True)

    def test_install_older_version_on_aur(self):
        set_module_args({
            'name': 'foo',
            'state': 'latest',
        })
        self.set_side_effect({
            '/usr/bin/aura --query --info foo': (0, "Version : 2", None),
            '/usr/bin/aura --aursync --info foo': (0, "Version  : 1", None),
            '/usr/bin/aura --aursync --builduser=nobody foo --noconfirm': (0, "Determining dependencies...", None)
        })
        self.execute_module(changed=True)
