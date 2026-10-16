import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('features',Path(__file__).with_name('compare-features.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class FeatureTests(unittest.TestCase):
    def test_operations_and_continuation(self):
        self.assertEqual(m.parse('QT_CONFIG = shared \\\n debug\nQT_CONFIG += ssl\nQT_CONFIG -= debug\n'),{'QT_CONFIG':{'shared','ssl'}})
    def test_missing_empty_key(self):
        changes=m.compare({'QT.xml.disabled_features':set()}, {})
        self.assertFalse(changes[0]['after_present'])
    def test_feature_disabled(self):
        before={'QT.gui.enabled_features':{'tabletevent'},'QT.gui.disabled_features':set()}
        after={'QT.gui.enabled_features':set(),'QT.gui.disabled_features':{'tabletevent'}}
        changes=m.compare(before,after)
        self.assertEqual(len(changes),2)
        self.assertEqual(changes[1]['removed'],['tabletevent'])
    def test_reject_dynamic(self):
        with self.assertRaises(ValueError):m.parse('QT_CONFIG += $$other')
    def test_reject_conditional(self):
        with self.assertRaises(ValueError):m.parse('win32:QT_CONFIG += ssl')
    def test_reject_unknown_assignment(self):
        with self.assertRaises(ValueError):m.parse('QT_CONFIG *= ssl')
    def test_order_is_not_change(self):
        self.assertEqual(m.compare(m.parse('QT_CONFIG = ssl shared'),m.parse('QT_CONFIG = shared ssl')),[])
    def test_cross_build_mode_only(self):
        key='qconfig.pri:QT.global.enabled_features'
        changes=m.compare({key:{'cross_compile','shared'}},{key:{'shared'}})
        capability,host=m.partition_host_mode(changes)
        self.assertEqual(capability,[])
        self.assertEqual(host,changes)
    def test_build_mode_cannot_hide_feature_loss(self):
        key='qconfig.pri:QT.global.enabled_features'
        changes=m.compare({key:{'cross_compile','shared'}},{key:set()})
        self.assertEqual(m.partition_host_mode(changes),(changes,[]))
    def test_build_mode_cannot_hide_missing_key(self):
        changes=m.compare({'qconfig.pri:QT.global.enabled_features':{'cross_compile'}},{})
        self.assertEqual(m.partition_host_mode(changes),(changes,[]))
    def test_build_mode_cannot_hide_module_change(self):
        key='qt_lib_gui.pri:QT.gui.enabled_features'
        changes=m.compare({key:{'cross_compile'}},{key:set()})
        self.assertEqual(m.partition_host_mode(changes),(changes,[]))
if __name__=='__main__':unittest.main()
