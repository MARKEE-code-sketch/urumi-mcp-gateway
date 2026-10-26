"""Deploy the approved theme to the owned local M10 shop without rerunning setup."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/evidence/ui-refresh/storefront'
NS = 'urumi-m10'
KUBE = ['kubectl', '--kubeconfig', str(ROOT / '.tools/m1/kubeconfig.yaml'), '--context', 'k3d-urumi', '-n', NS]
HELM = [str(ROOT / '.tools/m1/helm.exe')]
OPTS = ['--namespace', NS, '--kubeconfig', str(ROOT / '.tools/m1/kubeconfig.yaml'), '--kube-context', 'k3d-urumi']


def run(command, payload=None, timeout=60):
    result = subprocess.run(command, input=payload, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(command[:4]) + '; output withheld')
    return result.stdout


def wp(code):
    return json.loads(run(KUBE + ['exec', 'deployment/' + NS + '-wordpress', '--',
                                 'wp', '--allow-root', '--path=/var/www/html', 'eval', code]))


def resources():
    items = json.loads(run(KUBE + ['get', 'pods,pvc', '-o', 'json']))['items']
    return {'claims': sorted([{'name': x['metadata']['name'], 'uid': x['metadata']['uid'], 'phase': x['status']['phase']}
                              for x in items if x['kind'] == 'PersistentVolumeClaim'], key=lambda x: x['name']),
            'pods': {x['metadata']['labels']['app.kubernetes.io/component']: x['metadata']['uid']
                     for x in items if x['kind'] == 'Pod' and not x['metadata'].get('deletionTimestamp')}}


STATE = '''
echo wp_json_encode([
 'theme'=>get_stylesheet(),
 'settings'=>array_map('get_option', array_combine(
 ['home','siteurl','show_on_front','woocommerce_currency','woocommerce_cod_settings','woocommerce_cart_page_id','woocommerce_checkout_page_id','woocommerce_myaccount_page_id'],
 ['home','siteurl','show_on_front','woocommerce_currency','woocommerce_cod_settings','woocommerce_cart_page_id','woocommerce_checkout_page_id','woocommerce_myaccount_page_id'])),
 'products'=>array_map(function($p){return ['id'=>$p->get_id(),'sku'=>$p->get_sku(),'price'=>$p->get_price()];},wc_get_products(['limit'=>-1,'orderby'=>'ID','order'=>'ASC'])),
 'order_ids'=>wc_get_orders(['limit'=>-1,'return'=>'ids','orderby'=>'ID','order'=>'ASC']),
 'urls'=>['shop'=>wc_get_page_permalink('shop'),'cart'=>wc_get_cart_url(),'checkout'=>wc_get_checkout_url(),'account'=>wc_get_page_permalink('myaccount')]
]);
'''


def main(output=OUT):
    output = output.resolve()
    if not output.is_relative_to(ROOT / 'docs/evidence/ui-refresh'):
        raise ValueError('Evidence must stay inside docs/evidence/ui-refresh')
    output.mkdir(parents=True, exist_ok=True)
    before = wp(STATE)
    previous = resources()
    for file in (ROOT / 'deploy/charts/urumi/files/store-theme').glob('*.php'):
        run(KUBE + ['exec', '-i', 'deployment/' + NS + '-wordpress', '--', 'php', '-l', '/dev/stdin'], file.read_bytes())
    values = run(HELM + ['get', 'values', NS] + OPTS + ['--all', '-o', 'yaml'])
    private = ROOT / '.tools/operator/m10/values-storefront.yaml'
    private.write_bytes(values)
    history = json.loads(run(HELM + ['history', NS] + OPTS + ['-o', 'json']))
    baseline = {'shop': before, 'resources': previous, 'helm_revision': history[-1]['revision']}
    (output / ('before-revision-' + str(baseline['helm_revision']) + '.json')).write_text(json.dumps(baseline, indent=2) + '\n')
    run(HELM + ['upgrade', NS, str(ROOT / 'deploy/charts/urumi')] + OPTS +
        ['-f', str(private), '--wait', '--timeout', '180s'], timeout=210)
    run(KUBE + ['exec', 'deployment/' + NS + '-wordpress', '--', 'wp', '--allow-root', '--path=/var/www/html', 'theme', 'activate', 'urumi-shop'])
    after = wp(STATE)
    current = resources()
    assert after['theme'] == 'urumi-shop'
    assert {k: v for k, v in before.items() if k != 'theme'} == {k: v for k, v in after.items() if k != 'theme'}
    assert previous['claims'] == current['claims']
    assert {k: v for k, v in previous['pods'].items() if k != 'wordpress'} == {k: v for k, v in current['pods'].items() if k != 'wordpress'}
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'deploy/charts/urumi/files/store-theme').iterdir() if p.is_file()}
    actual = wp("$r=[]; foreach (glob(get_template_directory().'/*') as $p) { if(is_file($p)) $r[basename($p)]=hash_file('sha256',$p); } echo wp_json_encode($r);")
    assert hashes == actual
    result = {'status': 'PASS', 'prior_helm_revision': baseline['helm_revision'], 'prior_theme': before['theme'],
              'after': after, 'resources': current, 'other_six_pods_unchanged': True,
              'products_orders_settings_and_pvcs_preserved': True, 'deployed_sha256': hashes,
              'php_files_linted': len(list((ROOT / 'deploy/charts/urumi/files/store-theme').glob('*.php')))}
    (output / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'artifact': str(output.relative_to(ROOT) / 'deployment.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    main(parser.parse_args().output)
