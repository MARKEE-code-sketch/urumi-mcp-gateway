<?php defined('ABSPATH') || exit; ?>
</main>
<footer class="store-footer">
    <div class="site-wrap footer-inner">
        <div><a class="footer-brand" href="<?php echo esc_url(home_url('/')); ?>">urumi.</a><p>A little shop. A simple checkout.</p></div>
        <nav class="footer-links" aria-label="Shop links">
            <a href="<?php echo esc_url(wc_get_page_permalink('shop')); ?>">Shop</a>
            <a href="<?php echo esc_url(wc_get_cart_url()); ?>">Cart</a>
            <a href="<?php echo esc_url(wc_get_page_permalink('myaccount')); ?>">My account</a>
            <?php if (current_user_can('manage_woocommerce')) : ?><a href="<?php echo esc_url(admin_url()); ?>">Shop administration</a><?php endif; ?>
            <?php if (get_privacy_policy_url()) : ?><a href="<?php echo esc_url(get_privacy_policy_url()); ?>">Privacy policy</a><?php endif; ?>
        </nav>
        <small>&copy; <?php echo esc_html(wp_date('Y')); ?> Urumi shop</small>
    </div>
</footer>
<?php wp_footer(); ?>
</body>
</html>
