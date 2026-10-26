from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509.oid import ExtendedKeyUsageOID

from scripts.m10.local_https import FILES, HOSTS, prepare


def test_local_ca_and_leaf_are_scoped_and_valid(tmp_path):
    directory = tmp_path / "tls"
    metadata = prepare(directory)
    assert set(item.name for item in directory.iterdir()) == set(FILES)
    ca = x509.load_pem_x509_certificate((directory / "ca.pem").read_bytes())
    leaf = x509.load_pem_x509_certificate((directory / "tls.crt").read_bytes())
    constraints = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert constraints.critical
    assert constraints.value.permitted_subtrees == [x509.DNSName(".urumi.test")]
    assert constraints.value.excluded_subtrees is None
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length == 0
    assert ca.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign
    assert not ca.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature
    assert not leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == list(HOSTS)
    assert leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value == x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH])
    ca.public_key().verify(ca.signature, ca.tbs_certificate_bytes, padding.PKCS1v15(), ca.signature_hash_algorithm)
    ca.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes, padding.PKCS1v15(), leaf.signature_hash_algorithm)
    key = serialization.load_pem_private_key((directory / "tls.key").read_bytes(), None)
    assert key.public_key().public_numbers() == leaf.public_key().public_numbers()
    assert leaf.not_valid_after_utc - leaf.not_valid_before_utc == timedelta(days=30, minutes=5)
    assert ca.not_valid_after_utc - ca.not_valid_before_utc == timedelta(days=365, minutes=5)
    assert metadata["ca_sha256"] == ca.fingerprint(hashes.SHA256()).hex().upper()
    assert metadata["trust_installed"] is False


def test_existing_tls_identity_is_never_overwritten(tmp_path):
    directory = tmp_path / "tls"
    prepare(directory)
    original = {item.name: item.read_bytes() for item in directory.iterdir()}
    with pytest.raises(ValueError, match="TLS_DIRECTORY_ALREADY_EXISTS"):
        prepare(directory)
    assert original == {item.name: item.read_bytes() for item in directory.iterdir()}
