ARG CLI_IMAGE=wordpress:cli-2.12.0-php8.3
ARG WORDPRESS_IMAGE=wordpress:7.1.3-php8.3-apache
FROM ${CLI_IMAGE} AS cli
FROM ${WORDPRESS_IMAGE}
COPY --from=cli /usr/local/bin/wp /usr/local/bin/wp
ARG WOOCOMMERCE_VERSION=11.2.1
RUN apt-get update && apt-get install -y --no-install-recommends unzip curl && \
    curl --fail --show-error --location --proto '=https' --tlsv1.2 \
      "https://downloads.wordpress.org/plugin/woocommerce.${WOOCOMMERCE_VERSION}.zip" -o /tmp/woocommerce.zip && \
    sha256sum /tmp/woocommerce.zip && \
    unzip -q /tmp/woocommerce.zip -d /usr/src/wordpress/wp-content/plugins && \
    rm /tmp/woocommerce.zip && rm -rf /var/lib/apt/lists/*
COPY scripts/store/ /opt/urumi-store/
RUN curl --fail --show-error --location --proto '=https' --tlsv1.2 \
      "https://downloads.wordpress.org/plugin-checksums/woocommerce/${WOOCOMMERCE_VERSION}.json" -o /tmp/plugin-checksums.json && \
    php /opt/urumi-store/verify-package.php && rm /tmp/plugin-checksums.json
COPY scripts/store/live.php /usr/src/wordpress/urumi-live.php
COPY scripts/store/ready.php /usr/src/wordpress/urumi-ready.php
RUN printf 'memory_limit=256M\nupload_max_filesize=8M\npost_max_size=10M\n' > /usr/local/etc/php/conf.d/urumi.ini
