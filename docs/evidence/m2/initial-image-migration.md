# Initial demo image correction

The first image build seeded an owned 1x1 placeholder before the source correction to a visible 64x64 blue/orange demo picture. Persisted uploads intentionally do not change automatically when rebuilding an image.

A one-off operator script is prepared under ignored `.tools/m2/update-initial-demo-image.php`. It has not been executed by its author. It requires the `urumi_m2_attachment_id` marker, seed SKU `DEMO-001`, matching thumbnail/post-parent linkage, owned attachment title/path, exact original 1x1 dimensions and SHA256 `13cdf73d971c90b0394dd0a268b8b8d3f930ee7ca36f1a7d04c8d90ebb238346`. An unexpected state stops without changing the file.

The script replaces only this verified initial placeholder, regenerates WordPress image metadata, and preserves the product ID, attachment ID and image URL. It is intended before checkout/screenshots; it is not a general image migration or reset operation. Safe execution output records old/new hashes and IDs without credentials. Root records actual execution and post-change inspection separately. Fresh installs already use the corrected bootstrap image.
