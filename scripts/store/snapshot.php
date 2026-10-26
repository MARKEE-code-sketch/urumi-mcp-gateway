<?php
global $wpdb;
$id = wc_get_product_id_by_sku('DEMO-001');
$attachment = (int)get_option('urumi_m2_attachment_id');
$file = get_attached_file($attachment);
$orders = wc_get_orders(['limit'=>-1, 'return'=>'ids']);
sort($orders);
$safe_orders = [];
foreach ($orders as $order_id) {
    $order = wc_get_order($order_id);
    $items = [];
    foreach ($order->get_items() as $item) {
        $items[] = ['product_id'=>$item->get_product_id(), 'quantity'=>$item->get_quantity(), 'total'=>$item->get_total()];
    }
    $safe_orders[] = ['id'=>$order->get_id(), 'status'=>$order->get_status(), 'currency'=>$order->get_currency(), 'total'=>$order->get_total(), 'items'=>$items];
}
$product = wc_get_product($id);
$url = wp_get_attachment_url($attachment);
$parts = wp_parse_url($url);
$context = stream_context_create(['http'=>['header'=>"Host: shop.urumi.test\r\n", 'timeout'=>10, 'follow_location'=>0]]);
$bytes = file_get_contents('http://urumi-wordpress.urumi.svc.cluster.local' . $parts['path'], false, $context);
if ($bytes === false) { throw new RuntimeException('Saved image HTTP fetch failed'); }
$disk_hash = is_file($file) ? hash_file('sha256', $file) : null;
if (!$disk_hash || !hash_equals($disk_hash, hash('sha256', $bytes))) { throw new RuntimeException('Image HTTP bytes differ from saved file'); }
echo wp_json_encode(['product_id'=>(int)$id, 'product'=>['sku'=>$product->get_sku(), 'name'=>$product->get_name(), 'price'=>$product->get_price(), 'status'=>$product->get_status()], 'order_ids'=>$orders, 'orders'=>$safe_orders, 'attachment_id'=>$attachment, 'image_url'=>$url, 'image_sha256'=>$disk_hash, 'image_http_sha256'=>hash('sha256', $bytes), 'key_id'=>(int)get_option('urumi_m2_key_id'), 'currency'=>get_option('woocommerce_currency'), 'timezone'=>get_option('timezone_string'), 'cod'=>get_option('woocommerce_cod_settings')['enabled'] ?? 'no']) . "\n";
