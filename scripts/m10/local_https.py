"""Prepare project-only local TLS files; never install trust or change Kubernetes."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

HOSTS = ("dashboard-m10.urumi.test", "shop-m10.urumi.test")
FILES = ("ca-key.pem", "ca.pem", "tls.key", "tls.crt", "metadata.json")


def _write_new(path: Path, data: bytes) -> None:
    # Exclusive creation prevents silently replacing an already trusted identity.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def prepare(directory: Path) -> dict:
    """Create a constrained CA and server certificate in a fresh directory."""
    directory = directory.resolve()
    if directory.exists():
        raise ValueError("TLS_DIRECTORY_ALREADY_EXISTS: inspect it; do not replace a trusted CA")
    directory.mkdir(parents=True, mode=0o700)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Urumi local development CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.NameConstraints([x509.DNSName(".urumi.test")], None), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTS[0])]))
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host) for host in HOSTS]), critical=False)
        .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    for name, key in (("ca-key.pem", ca_key), ("tls.key", leaf_key)):
        _write_new(directory / name, key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    _write_new(directory / "ca.pem", ca.public_bytes(serialization.Encoding.PEM))
    _write_new(directory / "tls.crt", leaf.public_bytes(serialization.Encoding.PEM))
    metadata = {
        "hosts": list(HOSTS),
        "permitted_dns_suffix": ".urumi.test",
        "ca_sha256": ca.fingerprint(hashes.SHA256()).hex().upper(),
        "ca_sha1_thumbprint": ca.fingerprint(hashes.SHA1()).hex().upper(),
        "ca_expires": ca.not_valid_after_utc.isoformat(),
        "leaf_sha256": leaf.fingerprint(hashes.SHA256()).hex().upper(),
        "leaf_expires": leaf.not_valid_after_utc.isoformat(),
        "trust_installed": False,
    }
    _write_new(directory / "metadata.json", (json.dumps(metadata, indent=2) + "\n").encode())
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".tools/operator/m10/tls"))
    args = parser.parse_args()
    private_root = Path(__file__).resolve().parents[2] / ".tools"
    destination = args.directory.resolve()
    if not destination.is_relative_to(private_root.resolve()):
        parser.error("TLS files must stay under this project's ignored .tools directory")
    try:
        metadata = prepare(destination)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
