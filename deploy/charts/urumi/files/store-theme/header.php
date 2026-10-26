<?php defined('ABSPATH') || exit; ?>
<!doctype html>
<html <?php language_attributes(); ?>>
<head>
    <meta charset="<?php bloginfo('charset'); ?>">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
    <div class="site-wrap header-inner">
        <a class="brand" href="<?php echo esc_url(home_url('/')); ?>" aria-label="Urumi shop home">
            <img src="<?php echo esc_url(get_theme_file_uri('urumi-mark.svg')); ?>" alt="" width="36" height="36">
            <span>urumi<span class="brand-period">.</span><small>THE SHOP</small></span>
        </a>
        <nav class="primary-nav" aria-label="Main navigation">
            <a href="<?php echo esc_url(home_url('/')); ?>" <?php if (is_front_page()) echo 'aria-current="page"'; ?>>Home</a>
            <a href="<?php echo esc_url(wc_get_page_permalink('shop')); ?>" <?php if (is_shop() || is_product_category()) echo 'aria-current="page"'; ?>>All products</a>
        </nav>
        <div class="header-actions">
            <a class="account-link" href="<?php echo esc_url(wc_get_page_permalink('myaccount')); ?>"><?php urumi_icon('users-three'); ?>My account</a>
            <?php urumi_cart_link(); ?>
        </div>
    </div>
    <div class="site-wrap search-row">
        <form class="site-search" role="search" method="get" action="<?php echo esc_url(home_url('/')); ?>">
            <label class="screen-reader-text" for="store-search">Search products</label>
            <input id="store-search" type="search" name="s" value="<?php echo esc_attr(get_search_query()); ?>" placeholder="Find something in the shop">
            <input type="hidden" name="post_type" value="product">
            <button type="submit">Search</button>
        </form>
        <span class="search-note">Browse. Choose. Make it yours.</span>
    </div>
</header>
<main id="main" class="site-wrap">
