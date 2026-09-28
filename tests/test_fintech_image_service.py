import pytest

from src.fintech_image_service import ImageRequest, generate_and_share


def test_high_risk_request_is_rejected_before_network(monkeypatch):
    monkeypatch.delenv("INFRAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="approved risk level"):
        generate_and_share(ImageRequest("audit", "A payment dashboard", "high"))
