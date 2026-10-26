<?php
// --skip-wordpress allows initial installation; no secret values are returned.
$connection = new mysqli(explode(':', getenv('WORDPRESS_DB_HOST'))[0], getenv('WORDPRESS_DB_USER'), trim(file_get_contents(getenv('WORDPRESS_DB_PASSWORD_FILE'))), getenv('WORDPRESS_DB_NAME'));
$tables = $connection->query("SHOW TABLES LIKE 'wp_options'");
if (!$tables || !$tables->num_rows) { define('WP_INSTALLING', true); }
$connection->close();
require '/var/www/html/wp-load.php';
function secret_value($group, $key) {
    $value = trim(file_get_contents('/run/urumi/' . $group . '/' . $key));
    if ($value === '') { throw new RuntimeException('Required setup Secret is empty'); }
    return $value;
}
$canonical = getenv('STORE_CANONICAL_URL');
if (!is_blog_installed()) {
    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    wp_install('Urumi Demo Shop', secret_value('admin', 'username'), secret_value('admin', 'email'), true, '', secret_value('admin', 'password'));
    update_option('home', $canonical);
    update_option('siteurl', $canonical);
}
if (get_option('home') !== $canonical || get_option('siteurl') !== $canonical) {
    throw new RuntimeException('Canonical shop URL mismatch; reconcile before setup');
}
if (get_bloginfo('version') !== '7.1.3') { throw new RuntimeException('WordPress version differs from approved pin'); }
require_once ABSPATH . 'wp-admin/includes/plugin.php';
$plugin = 'woocommerce/woocommerce.php';
if (get_plugin_data(WP_PLUGIN_DIR . '/' . $plugin)['Version'] !== '11.2.1') {
    throw new RuntimeException('WooCommerce version differs from approved pin');
}
if (!is_plugin_active($plugin)) {
    $activation = activate_plugin($plugin);
    if (is_wp_error($activation)) { throw new RuntimeException('WooCommerce activation failed'); }
}
// Activation needs a fresh process before WooCommerce classes are available.
if (!class_exists('WooCommerce')) { WP_CLI::success('Plugin activated; continue configuration in next process'); return; }
$options = [
    'woocommerce_coming_soon' => 'no',
    'timezone_string' => 'Asia/Kolkata', 'woocommerce_currency' => 'INR',
    'woocommerce_default_country' => 'IN:DL', 'woocommerce_store_address' => 'Demo Street',
    'woocommerce_store_city' => 'New Delhi', 'woocommerce_store_postcode' => '110001',
    'woocommerce_enable_guest_checkout' => 'yes', 'woocommerce_calc_taxes' => 'no',
    'woocommerce_cod_settings' => ['enabled' => 'yes', 'title' => 'Cash on delivery', 'enable_for_virtual' => 'yes'],
];
foreach ($options as $name => $value) { update_option($name, $value); }
global $wp_rewrite;
$wp_rewrite->set_permalink_structure('/%postname%/');
$wp_rewrite->flush_rules(true);
WC_Install::create_pages();
foreach (['cart' => '[woocommerce_cart]', 'checkout' => '[woocommerce_checkout]'] as $page => $content) {
    $id = get_option('woocommerce_' . $page . '_page_id');
    if ($id) { wp_update_post(['ID' => $id, 'post_content' => $content]); }
}
$product_id = wc_get_product_id_by_sku('DEMO-001');
if (!$product_id) {
    $product = new WC_Product_Simple();
    $product->set_name('Urumi Demo Product'); $product->set_sku('DEMO-001');
    $product->set_regular_price('499.00'); $product->set_status('publish'); $product->set_virtual(true);
    $product_id = $product->save();
}
if (!get_option('urumi_m2_attachment_id')) {
    require_once ABSPATH . 'wp-admin/includes/file.php';
    require_once ABSPATH . 'wp-admin/includes/media.php';
    require_once ABSPATH . 'wp-admin/includes/image.php';
    $image = imagecreatetruecolor(64, 64);
    imagefill($image, 0, 0, imagecolorallocate($image, 35, 85, 145));
    imagefilledrectangle($image, 16, 16, 47, 47, imagecolorallocate($image, 245, 165, 45));
    ob_start(); imagepng($image); $png = ob_get_clean(); imagedestroy($image);
    $upload = wp_upload_bits('urumi-demo.png', null, $png);
    if ($upload['error']) { throw new RuntimeException('Demo image upload failed'); }
    $attachment = wp_insert_attachment(['post_mime_type'=>'image/png', 'post_title'=>'Urumi demo image', 'post_status'=>'inherit'], $upload['file'], $product_id, true);
    if (is_wp_error($attachment)) { throw new RuntimeException('Demo image attachment failed'); }
    wp_update_attachment_metadata($attachment, wp_generate_attachment_metadata($attachment, $upload['file']));
    update_option('urumi_m2_attachment_id', $attachment);
    set_post_thumbnail($product_id, $attachment);
}
$user = get_user_by('login', 'urumi-integration');
if (!$user) {
    $user_id = wp_insert_user(['user_login'=>'urumi-integration', 'user_pass'=>wp_generate_password(48, true, true), 'role'=>'shop_manager', 'user_email'=>'integration@example.invalid']);
    if (is_wp_error($user_id)) { throw new RuntimeException('Integration identity creation failed'); }
    $user = get_user_by('id', $user_id);
}
if (!in_array('shop_manager', $user->roles, true)) { throw new RuntimeException('Integration role mismatch'); }
global $wpdb;
$table = $wpdb->prefix . 'woocommerce_api_keys';
$rows = $wpdb->get_results($wpdb->prepare("SELECT * FROM {$table} WHERE description = %s", 'urumi-m2-integration'));
$marker = get_option('urumi_m2_key_id');
$consumer_key = secret_value('rest', 'consumer-key');
$consumer_secret = secret_value('rest', 'consumer-secret');
if (count($rows) > 1 || ($marker && count($rows) !== 1)) { throw new RuntimeException('Key state inconsistent or revoked; manual reconciliation required'); }
if (!$rows) {
    $ok = $wpdb->insert($table, ['user_id'=>$user->ID, 'description'=>'urumi-m2-integration', 'permissions'=>'read_write', 'consumer_key'=>wc_api_hash($consumer_key), 'consumer_secret'=>$consumer_secret, 'truncated_key'=>substr($consumer_key, -7)]);
    if (!$ok) { throw new RuntimeException('REST key creation failed'); }
    $key_id = $wpdb->insert_id;
} else {
    $row = $rows[0];
    if (!hash_equals($row->consumer_key, wc_api_hash($consumer_key)) || !hash_equals($row->consumer_secret, $consumer_secret) || (int)$row->user_id !== (int)$user->ID || $row->permissions !== 'read_write' || ($marker && (int)$marker !== (int)$row->key_id)) {
        throw new RuntimeException('Existing REST credential mismatch; manual reconciliation required');
    }
    $key_id = $row->key_id;
}
update_option('urumi_m2_key_id', (int)$key_id);
echo wp_json_encode(['product_id'=>(int)$product_id, 'attachment_id'=>(int)get_option('urumi_m2_attachment_id'), 'key_id'=>(int)$key_id, 'currency'=>get_option('woocommerce_currency'), 'timezone'=>get_option('timezone_string')]) . "\n";
