from zotero_to_md.extract_web import extract_web_text


def test_extract_web_text_sanitizes_null_bytes_before_readability(monkeypatch) -> None:
    monkeypatch.setattr(
        "zotero_to_md.extract_web.trafilatura.fetch_url", lambda _url: "ab\x00c"
    )
    monkeypatch.setattr(
        "zotero_to_md.extract_web.trafilatura.extract", lambda *_args, **_kwargs: None
    )

    class FakeDocument:
        def __init__(self, payload: str) -> None:
            assert "\x00" not in payload
            self.payload = payload

        def summary(self) -> str:
            return "<article><p>Hello Web</p></article>"

    monkeypatch.setattr("zotero_to_md.extract_web.Document", FakeDocument)

    text, error = extract_web_text("https://example.com")

    assert error is None
    assert text == "Hello Web"
