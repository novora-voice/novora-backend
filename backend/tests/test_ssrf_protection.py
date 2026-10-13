import pytest
from novora.adapters.knowledge.security import validate_destination_endpoint
from novora.core.exceptions import SSRFSecurityError

def test_ssrf_blocks_loopback_addresses():
    with pytest.raises(SSRFSecurityError, match="loopback"):
        validate_destination_endpoint("http://127.0.0.1:8000/vector")

    with pytest.raises(SSRFSecurityError, match="Forbidden hostname 'localhost'"):
        validate_destination_endpoint("http://localhost:8080/graph")

def test_ssrf_blocks_cloud_metadata_ip():
    with pytest.raises(SSRFSecurityError, match="link-local|metadata"):
        validate_destination_endpoint("http://169.254.169.254/latest/meta-data")

def test_ssrf_blocks_private_rfc1918_ips():
    with pytest.raises(SSRFSecurityError, match="private RFC1918"):
        validate_destination_endpoint("http://10.0.0.5:8000/data")

    with pytest.raises(SSRFSecurityError, match="private RFC1918"):
        validate_destination_endpoint("http://192.168.1.100:6379")

def test_ssrf_blocks_forbidden_schemes():
    with pytest.raises(SSRFSecurityError, match="Forbidden scheme 'file'"):
        validate_destination_endpoint("file:///etc/passwd")

    with pytest.raises(SSRFSecurityError, match="Forbidden scheme 'gopher'"):
        validate_destination_endpoint("gopher://internal.server:70")

def test_ssrf_permits_valid_public_endpoint():
    # Public domain with HTTPS should pass
    validate_destination_endpoint("https://api.pinecone.io/indexes")
