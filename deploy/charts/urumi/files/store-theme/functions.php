<?php
defined('ABSPATH') || exit;
require_once get_theme_file_path('admin.php');

// Keep WordPress's editor toolbar and remote avatars off the customer storefront.
add_filter('show_admin_bar', function ($show) { return is_admin() ? $show : false; });

add_action('after_setup_theme', function () {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support('woocommerce');
    add_theme_support('wc-product-gallery-slider');
    add_theme_support('wc-product-gallery-lightbox');
    add_theme_support('html5', ['search-form', 'gallery', 'caption', 'style', 'script']);
});

add_action('wp_enqueue_scripts', function () {
    wp_enqueue_style('urumi-shop', get_stylesheet_uri(), [], filemtime(get_template_directory() . '/style.css'));
    // WooCommerce loads this on demand; our shared header needs its cart events.
    wp_enqueue_script('wc-cart-fragments');
}, 20);

add_action('wp_head', function () {
    echo '<link rel="icon" type="image/svg+xml" href="' . esc_url(get_theme_file_uri('urumi-mark.svg')) . '">';
});

function urumi_icon($name) {
    $icons = ['package', 'users-three', 'magnifying-glass', 'arrow-up-right', 'receipt'];
    if (in_array($name, $icons, true)) {
        echo '<img class="icon" src="' . esc_url(get_theme_file_uri($name . '.svg')) . '" alt="" width="22" height="22">';
    }
}

function urumi_cart_link() {
    $count = WC()->cart ? WC()->cart->get_cart_contents_count() : 0;
    echo '<a class="cart-link" href="' . esc_url(wc_get_cart_url()) . '">';
    urumi_icon('package');
    echo 'Cart <span class="cart-count">' . esc_html($count) . '</span></a>';
}

add_filter('woocommerce_add_to_cart_fragments', function ($fragments) {
    ob_start();
    urumi_cart_link();
    $fragments['a.cart-link'] = ob_get_clean();
    return $fragments;
});

add_filter('loop_shop_columns', function () { return 3; });
remove_action('woocommerce_sidebar', 'woocommerce_get_sidebar', 10);
