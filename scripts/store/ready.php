<?php
ini_set('display_errors', '0');
try {
    $connection = new mysqli(explode(':', getenv('WORDPRESS_DB_HOST'))[0], getenv('WORDPRESS_DB_USER'), trim(file_get_contents(getenv('WORDPRESS_DB_PASSWORD_FILE'))), getenv('WORDPRESS_DB_NAME'));
    $installed = $connection->query("SELECT option_value FROM wp_options WHERE option_name='siteurl'");
    if (!$installed || !$installed->num_rows) { http_response_code(503); exit; }
    $connection->close();
    require __DIR__ . '/wp-load.php';
    global $wpdb;
    $ok = is_blog_installed() && class_exists('WooCommerce') && $wpdb->get_var('SELECT 1') === '1';
    http_response_code($ok ? 200 : 503);
} catch (Throwable $error) {
    http_response_code(503);
}
