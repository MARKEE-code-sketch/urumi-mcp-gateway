<?php
defined('ABSPATH') || exit;

function urumi_admin_styles() {
    wp_enqueue_style('urumi-shop-admin', get_theme_file_uri('admin.css'), [], filemtime(get_theme_file_path('admin.css')));
}
add_action('admin_enqueue_scripts', 'urumi_admin_styles', 100);
add_action('login_enqueue_scripts', 'urumi_admin_styles', 100);

add_filter('login_headerurl', function () { return home_url('/'); });
add_filter('login_headertext', function () { return 'Urumi shop administration'; });

function urumi_admin_favicon() {
    echo '<link rel="icon" type="image/svg+xml" href="' . esc_url(get_theme_file_uri('urumi-mark.svg')) . '">';
}
add_action('admin_head', 'urumi_admin_favicon');
add_action('login_head', 'urumi_admin_favicon');

function urumi_shop_overview() {
    if (!current_user_can('manage_woocommerce') || !function_exists('wc_get_orders')) {
        return;
    }
    $products = wc_get_products(['limit' => 1, 'paginate' => true]);
    $orders = wc_get_orders(['limit' => 1, 'paginate' => true]);
    ?>
    <div class="urumi-admin-overview">
        <div class="urumi-admin-intro">
            <div><span class="urumi-admin-eyebrow">URUMI SHOP</span><h2>Your shop, at a glance.</h2><p>Manage your collection, follow orders and keep your shop up to date.</p></div>
            <img class="urumi-admin-mark" src="<?php echo esc_url(get_theme_file_uri('urumi-mark.svg')); ?>" width="48" height="48" alt="">
        </div>
        <div class="urumi-admin-metrics">
            <?php if (current_user_can('edit_products')) : ?>
            <a class="urumi-admin-metric" href="<?php echo esc_url(admin_url('edit.php?post_type=product')); ?>"><span class="dashicons dashicons-products" aria-hidden="true"></span><strong><?php echo esc_html(number_format_i18n($products->total)); ?></strong><span>Products</span></a>
            <?php endif; ?>
            <?php if (current_user_can('edit_shop_orders')) : ?>
            <a class="urumi-admin-metric" href="<?php echo esc_url(admin_url('admin.php?page=wc-orders')); ?>"><span class="dashicons dashicons-cart" aria-hidden="true"></span><strong><?php echo esc_html(number_format_i18n($orders->total)); ?></strong><span>Orders</span></a>
            <?php endif; ?>
        </div>
        <div class="urumi-admin-actions">
            <?php if (current_user_can('edit_products')) : ?><a class="button button-primary" href="<?php echo esc_url(admin_url('edit.php?post_type=product')); ?>">Manage products</a><?php endif; ?>
            <a class="button" href="<?php echo esc_url(home_url('/')); ?>">View shop</a>
            <a class="button" href="<?php echo esc_url(admin_url('admin.php?page=wc-settings')); ?>">Shop settings</a>
        </div>
    </div>
    <?php
}

add_action('wp_dashboard_setup', function () {
    if (current_user_can('manage_woocommerce') && function_exists('wc_get_orders')) {
        // This local shop does not need WordPress's internet-backed news feed.
        remove_meta_box('dashboard_primary', 'dashboard', 'side');
        remove_action('welcome_panel', 'wp_welcome_panel');
        add_action('welcome_panel', 'urumi_shop_overview');
        // Respect a user's dismissed welcome panel while keeping the overview available.
        if (get_user_meta(get_current_user_id(), 'show_welcome_panel', true) === '0') {
            wp_add_dashboard_widget('urumi_shop_overview', 'Shop overview', 'urumi_shop_overview', null, null, 'normal', 'high');
        }
    }
});
