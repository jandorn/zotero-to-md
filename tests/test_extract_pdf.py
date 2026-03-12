from zotero_to_md.extract_pdf import _repair_shifted_pdf_text


def test_repair_shifted_pdf_text_repairs_shifted_excerpt() -> None:
    shifted = (
        "\x03&RUUHVSRQGLQJ\x03DXWKRU\x11\x03$EVWUDFW\x03\n"
        "7KH\x03UHQXQFLDWLRQ\x03RI\x03IRVVLO\x03HQHUJLHV"
    )

    repaired = _repair_shifted_pdf_text(shifted)

    assert "Corresponding author." in repaired
    assert "Abstract" in repaired
    assert "The renunciation of fossil energies" in repaired


def test_repair_shifted_pdf_text_repairs_keywords_line() -> None:
    shifted = "Keywords:\x03(QHUJ\\\x03IOH[LELOLW\\\x03VLPXODWLRQ"

    repaired = _repair_shifted_pdf_text(shifted)

    assert repaired == "Keywords: Energy flexibility simulation"


def test_repair_shifted_pdf_text_preserves_readable_text() -> None:
    original = "Peer-review under responsibility of the scientific committee."

    assert _repair_shifted_pdf_text(original) == original
