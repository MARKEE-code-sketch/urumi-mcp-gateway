<?php
defined('ABSPATH') || exit;
get_header();
$featured = wc_get_products(['status' => 'publish', 'limit' => 1, 'orderby' => 'date', 'order' => 'ASC', 'visibility' => 'catalog', 'stock_status' => 'instock']);
?>
<section class="store-hero" aria-labelledby="welcome-title">
    <div class="hero-copy">
        <span class="eyebrow">WELCOME TO URUMI</span>
        <h1 id="welcome-title">Find your next<br>little favourite.</h1>
        <p>Explore the collection, take a closer look, and find something for you.</p>
        <div class="hero-actions"><a class="button" href="<?php echo esc_url(wc_get_page_permalink('shop')); ?>">Explore the shop <?php urumi_icon('arrow-up-right'); ?></a></div>
    </div>
    <?php if ($featured) : $pick = $featured[0]; ?>
    <a class="hero-product" href="<?php echo esc_url($pick->get_permalink()); ?>">
        <span class="eyebrow">FROM THE COLLECTION</span>
        <?php echo $pick->get_image('woocommerce_single'); ?>
        <div><h2><?php echo esc_html($pick->get_name()); ?></h2><span class="price"><?php echo wp_kses_post($pick->get_price_html()); ?></span></div>
        <span class="product-detail-link">Take a closer look <?php urumi_icon('arrow-up-right'); ?></span>
    </a>
    <?php endif; ?>
</section>
<section class="home-catalog" aria-labelledby="collection-title">
    <div class="section-heading"><div><span class="section-kicker">THE COLLECTION</span><h2 id="collection-title">A look around the shop</h2></div><a href="<?php echo esc_url(wc_get_page_permalink('shop')); ?>">View all products <?php urumi_icon('arrow-up-right'); ?></a></div>
    <?php echo do_shortcode('[products limit="6" columns="3" orderby="date" order="DESC" visibility="visible"]'); ?>
</section>
<?php get_footer(); ?>
