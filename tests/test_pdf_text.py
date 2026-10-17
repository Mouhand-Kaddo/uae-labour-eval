import pytest

from eval_harness.pdf_text import Glyph, page_lines

WIDTH = 6.0


def line(visual, baseline=700.0, size=16.0):
    """Glyphs laid out left to right as a PDF draws them; each item is one glyph's text."""
    return [
        Glyph(text, 100 + i * WIDTH, 100 + (i + 1) * WIDTH, baseline, size)
        for i, text in enumerate(visual)
    ]


@pytest.mark.parametrize(
    ("visual", "logical"),
    [
        (["ر", "ج", "لأ", "ا"], "الأجر"),
        (["ت", "ا", "ق", "لا", "ع"], "علاقات"),
        (["ة", "د", "ا", "لم", "ا"], "المادة"),
    ],
)
def test_a_right_to_left_line_is_reversed_a_whole_glyph_at_a_time(visual, logical):
    assert page_lines(line(visual)) == [logical]


def test_numbers_inside_a_right_to_left_line_keep_their_digit_order():
    visual = [*"2021 ةنسل )33( مقر"]

    assert page_lines(line(visual)) == ["رقم (33) لسنة 2021"]


def test_a_number_with_separators_stays_whole_and_separate_numbers_keep_their_order():
    assert page_lines(line([*"مهرد 200.000"])) == ["200.000 درهم"]
    assert page_lines(line([*"1,000 نم رثكأ"])) == ["أكثر من 1,000"]
    assert page_lines(line([*"90 ىلإ 30 نم"])) == ["من 30 إلى 90"]


def test_latin_words_inside_a_right_to_left_line_read_left_to_right():
    assert page_lines(line([*"ديدجلا Labour Law نوناق"])) == ["قانون Labour Law الجديد"]
    assert page_lines(line([*"PDF 2 فلم"])) == ["ملف 2 PDF"]


def test_a_line_without_right_to_left_text_is_left_as_drawn():
    assert page_lines(line([*"Article (1) of 2021"])) == ["Article (1) of 2021"]


def test_glyphs_are_grouped_into_lines_by_baseline_from_top_to_bottom():
    second = line([*"يناث"], baseline=678)
    first = line([*"لوأ"], baseline=704)
    nudged_down = Glyph("ر", 120, 126, 703, 16)

    assert page_lines(second + first + [nudged_down]) == ["رأول", "ثاني"]


def test_a_page_without_letters_has_no_lines():
    assert page_lines([]) == []
    assert page_lines([Glyph("ً", 99, 99, 708.8, 16), Glyph("", 100, 104, 700, 16)]) == []


def test_a_raised_diacritic_follows_the_letter_it_sits_on():
    tanween_left_of_alef = Glyph("ً", 99, 99, 708.8, 16)
    damma_over_teh = Glyph("ُ", 121, 121, 706, 16)

    assert page_lines([*line([*"ادقن"]), tanween_left_of_alef]) == ["نقداً"]
    assert page_lines([*line([*"بسحت"]), damma_over_teh]) == ["تُحسب"]
