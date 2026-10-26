<?php
$metadata = json_decode(file_get_contents('/tmp/plugin-checksums.json'), true, 512, JSON_THROW_ON_ERROR);
if (empty($metadata['files'])) { throw new RuntimeException('Publisher checksum list missing'); }
foreach ($metadata['files'] as $file => $hashes) {
    if (str_contains($file, '..') || str_starts_with($file, '/')) { throw new RuntimeException('Invalid checksum path'); }
    $path = '/usr/src/wordpress/wp-content/plugins/woocommerce/' . $file;
    $algorithm = isset($hashes['sha256']) ? 'sha256' : 'md5';
    if (!isset($hashes[$algorithm]) || !is_file($path) || !hash_equals($hashes[$algorithm], hash_file($algorithm, $path))) {
        throw new RuntimeException('Publisher plugin checksum mismatch');
    }
}
echo 'Publisher plugin checksums verified: ' . count($metadata['files']) . " files\n";
