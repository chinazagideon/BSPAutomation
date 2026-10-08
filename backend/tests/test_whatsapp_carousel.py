import asyncio
import pytest
from pydantic import ValidationError

from app.adapters.base import CarouselCard, CarouselMessage
from app.adapters.whatsapp import MockWhatsAppBSPAdapter, MetaCloudWhatsAppAdapter


def _card(i=0, header_type="image", body="Item"):
    return CarouselCard(
        header_type=header_type,
        media_url=f"https://cdn.example.com/{i}.jpg",
        body_text=body,
        cta_text="Buy",
        cta_url=f"https://shop.example.com/{i}",
    )


def test_requires_two_to_ten_cards():
    with pytest.raises(ValidationError):
        CarouselMessage(body_text="Hi", cards=[_card()])
    with pytest.raises(ValidationError):
        CarouselMessage(body_text="Hi", cards=[_card(i) for i in range(11)])
    assert len(CarouselMessage(body_text="Hi", cards=[_card(0), _card(1)]).cards) == 2


def test_rejects_mixed_header_types():
    with pytest.raises(ValidationError):
        CarouselMessage(body_text="Hi", cards=[_card(0), _card(1, header_type="video")])


def test_rejects_long_card_body():
    with pytest.raises(ValidationError):
        _card(body="x" * 161)


def test_mock_records_carousel():
    adapter = MockWhatsAppBSPAdapter()
    msg = CarouselMessage(body_text="Hi", cards=[_card(0), _card(1)])
    result = asyncio.run(adapter.send_interactive_carousel("2348000000000", msg))
    assert result["message_id"].startswith("wamid.mock.carousel")
    assert len(result["cards"]) == 2


def test_meta_payload_shape():
    captured = {}

    class FakeAdapter(MetaCloudWhatsAppAdapter):
        def __init__(self):
            self.phone_number_id = "123"

        async def _execute_meta_egress(self, payload, phone_number_id=None):
            captured.update(payload)
            return "wamid.1"

    msg = CarouselMessage(body_text="Hi", cards=[_card(0, "video"), _card(1, "video")])
    asyncio.run(FakeAdapter().send_interactive_carousel("234800", msg))
    interactive = captured["interactive"]
    assert interactive["type"] == "carousel"
    card0 = interactive["action"]["cards"][0]
    assert card0["card_index"] == 0
    assert card0["header"] == {"type": "video", "video": {"link": "https://cdn.example.com/0.jpg"}}
    assert card0["action"]["name"] == "cta_url"
