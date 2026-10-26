<?php
defined('ABSPATH') || exit;
get_header();
if (have_posts()) {
    while (have_posts()) {
        the_post();
        echo '<article class="page-content">';
        the_title('<h1 class="page-title">', '</h1>');
        the_content();
        wp_link_pages();
        echo '</article>';
    }
} else {
    echo '<section class="page-content"><h1>Page not found</h1><p>Try searching for a product or return to the shop.</p><a class="button" href="' . esc_url(wc_get_page_permalink('shop')) . '">Browse products</a></section>';
}
get_footer();
