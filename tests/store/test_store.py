"""Offline deployment-boundary checks; live store checks remain separate."""
import importlib.util
import base64
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('rest_check', ROOT / 'scripts/m2/rest-check.py')
rest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rest)


class StoreChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helm = ROOT / '.tools/m1/helm.exe'
        cls.chart = ROOT / 'deploy/charts/urumi'
        cls.enabled = cls.render('--set', 'store.enabled=true', '-f', str(cls.chart / 'values-module-local.yaml'))

    @classmethod
    def render(cls, *args):
        return subprocess.run([str(cls.helm), 'template', 'urumi', str(cls.chart), *args], check=True, capture_output=True, text=True).stdout

    def test_store_is_opt_in(self):
        self.assertNotIn('urumi-wordpress', self.render())

    def test_disks_are_retained_separately(self):
        claims = [piece for piece in self.enabled.split('---') if 'kind: PersistentVolumeClaim' in piece]
        self.assertEqual(len(claims), 2)
        for claim in claims:
            self.assertIn('helm.sh/resource-policy: keep', claim)
            self.assertIn('ReadWriteOnce', claim)
        self.assertIn('urumi-mariadb-data', self.enabled)
        self.assertIn('urumi-wordpress-content', self.enabled)

    def test_only_storefront_is_public(self):
        self.assertEqual(self.enabled.count('kind: Ingress'), 1)
        self.assertIn('host: shop.urumi.test', self.enabled)
        self.assertNotIn('NodePort', self.enabled)
        self.assertNotIn('LoadBalancer', self.enabled)
        self.assertNotIn('kind: Secret', self.enabled)

    def test_workloads_have_health_resources_and_no_api_token(self):
        for piece in self.enabled.split('---'):
            if 'kind: Deployment' in piece or 'kind: StatefulSet' in piece:
                for expected in ('readinessProbe:', 'livenessProbe:', 'requests:', 'limits:', 'automountServiceAccountToken: false'):
                    self.assertIn(expected, piece)

    def test_policy_does_not_allow_entire_namespace(self):
        policy = next(piece for piece in self.enabled.split('---') if 'kind: NetworkPolicy' in piece)
        self.assertNotIn('namespaceSelector:', policy)
        self.assertNotIn('podSelector: {}', policy)
        self.assertIn('urumi-m2-access: setup', policy)

    def test_production_uses_same_store_templates(self):
        rendered = self.render('-f', str(self.chart / 'values-module-prod.yaml'), '--set', 'store.enabled=true')
        self.assertIn('kind: StatefulSet', rendered)
        self.assertIn('kind: Deployment', rendered)
        self.assertIn('host: shop.example.com', rendered)

    @staticmethod
    def theme_resources(rendered):
        resources = [item for item in yaml.safe_load_all(rendered) if item]
        deployment = next(item for item in resources if item['kind'] == 'Deployment'
                          and item['metadata']['name'].endswith('-wordpress'))
        pod = deployment['spec']['template']
        container = next(item for item in pod['spec']['containers'] if item['name'] == 'wordpress')
        mount = next(item for item in container['volumeMounts']
                     if item['mountPath'] == '/var/www/html/wp-content/themes/urumi-shop')
        volume = next(item for item in pod['spec']['volumes'] if item['name'] == mount['name'])
        config = next(item for item in resources if item['kind'] == 'ConfigMap'
                      and item['metadata']['name'] == volume['configMap']['name'])
        return pod, container, mount, config

    def test_theme_mount_is_read_only_and_preserves_content_volume(self):
        pod, container, mount, _ = self.theme_resources(self.enabled)
        self.assertIs(mount['readOnly'], True)
        self.assertNotIn('subPath', mount)
        self.assertIn({'name': 'content', 'mountPath': '/var/www/html'}, container['volumeMounts'])
        content = next(item for item in pod['spec']['volumes'] if item['name'] == 'content')
        self.assertEqual(content['persistentVolumeClaim']['claimName'], 'urumi-wordpress-content')

    def test_theme_configmap_preserves_all_text_and_font_bytes(self):
        _, _, _, config = self.theme_resources(self.enabled)
        source = self.chart / 'files/store-theme'
        files = [path for path in source.iterdir() if path.is_file()]
        self.assertTrue(any(path.suffix == '.ttf' for path in files), 'Local font is required')
        self.assertTrue(any(path.name == 'functions.php' for path in files))
        text = config.get('data', {})
        binary = config.get('binaryData', {})
        self.assertEqual(set(text) | set(binary), {path.name for path in files})
        for path in files:
            if path.name in binary:
                self.assertEqual(base64.b64decode(binary[path.name], validate=True), path.read_bytes())
            else:
                self.assertEqual(text[path.name].rstrip('\r\n'),
                                 path.read_bytes().decode('utf-8').rstrip('\r\n'))
        # Kubernetes ConfigMaps have a 1 MiB limit; leave room for their metadata.
        self.assertLess(sum(len(value.encode()) for value in text.values())
                        + sum(len(base64.b64decode(value)) for value in binary.values()), 900_000)

    def test_theme_is_opt_in_for_both_resources_and_mount(self):
        rendered = self.render()
        self.assertNotIn('/wp-content/themes/urumi-shop', rendered)
        self.assertNotIn('Theme Name: Urumi', rendered)

    def test_theme_changes_trigger_rollout_and_are_not_helm_templates(self):
        before, _, _, _ = self.theme_resources(self.enabled)
        checksums = {key: value for key, value in before['metadata'].get('annotations', {}).items()
                     if 'checksum' in key and 'theme' in key}
        self.assertTrue(checksums, 'Theme checksum must trigger rollout when mounted assets change')
        for value in checksums.values():
            self.assertRegex(value, r'^[a-f0-9]{64}$')
        with tempfile.TemporaryDirectory(prefix='urumi-theme-chart-') as directory:
            chart = Path(directory) / 'urumi'
            shutil.copytree(self.chart, chart)
            marker = '\n/* {{ deliberately_not_a_helm_function }} */\n'
            style = chart / 'files/store-theme/style.css'
            style.write_text(style.read_text(encoding='utf-8') + marker, encoding='utf-8')
            changed = subprocess.run([str(self.helm), 'template', 'urumi', str(chart),
                                      '--set', 'store.enabled=true', '-f',
                                      str(chart / 'values-module-local.yaml')],
                                     check=True, capture_output=True, text=True).stdout
            after, _, _, config = self.theme_resources(changed)
            self.assertIn(marker.strip(), config['data']['style.css'])
            for key, value in checksums.items():
                self.assertNotEqual(after['metadata']['annotations'].get(key), value)
            font = next((chart / 'files/store-theme').glob('*.ttf'))
            font.write_bytes(font.read_bytes() + b'checksum-regression-marker')
            changed_font = subprocess.run([str(self.helm), 'template', 'urumi', str(chart),
                                           '--set', 'store.enabled=true', '-f',
                                           str(chart / 'values-module-local.yaml')],
                                          check=True, capture_output=True, text=True).stdout
            after_font, _, _, _ = self.theme_resources(changed_font)
            for key in checksums:
                self.assertNotEqual(after_font['metadata']['annotations'].get(key),
                                    after['metadata']['annotations'].get(key))


class SigningBoundaryTests(unittest.TestCase):
    def test_method_canonical_origin_and_query_are_bound(self):
        args = ('GET', 'http://shop.urumi.test/wp-json/wc/v3/products', {'context': 'edit', 'search': 'a b&c'}, 'ck_fake', 'cs_fake', 'fixed_nonce', 123456)
        baseline = rest.signature(*args)
        for index, changed in ((0, 'POST'), (1, 'http://other.test/wp-json/wc/v3/products'), (2, {'context': 'edit', 'search': 'other'}), (4, 'different_secret')):
            modified = list(args)
            modified[index] = changed
            self.assertNotEqual(baseline, rest.signature(*modified))
        self.assertNotIn('cs_fake', baseline)
        self.assertNotIn('oauth_version', baseline)
        self.assertIn('HMAC-SHA256', baseline)


if __name__ == '__main__':
    unittest.main()
