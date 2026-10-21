"""Regression guard for the generated Jekyll stylesheet (root or /site build)."""

import colorsys
import re
import sys
import unittest
from pathlib import Path


CSS = (Path(sys.argv[1]) / "assets/css/style.css").read_text(encoding="utf-8")
# The selectors under test are ordinary top-level CSS rules, not media-query rules.
RULES = [(selector.strip(), dict(re.findall(r"((?:--)?[\w-]+)\s*:\s*([^;]+);", body)))
         for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS)]


def declarations(selector):
    result = {}
    for names, values in RULES:
        if selector in (name.strip() for name in names.split(",")):
            result.update(values)
    return result


def rgb(value, variables):
    value = value.strip()
    while value.startswith("var("):
        value = variables[value[4:-1].strip()].strip()
    match = re.fullmatch(r"#([\da-fA-F]{6})", value)
    if not match:
        raise AssertionError(f"Cor CSS não suportada no teste: {value!r}")
    hex_color = match[1]
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(color):
    linear = [(channel / 12.92 if channel <= 0.04045 else
               ((channel + 0.055) / 1.055) ** 2.4) for channel in color]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class CrimsonAccentsTest(unittest.TestCase):
    def test_primary_action_is_crimson_and_readable_in_both_themes(self):
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                variables = declarations(":root")
                if theme == "light":
                    variables.update(declarations(':root[data-theme="light"]'))
                self.assertIn("--black", variables, "Tema não encontrado no CSS gerado")
                for state, selector in (("normal", ".button-primary"),
                                        ("hover/focus", ".button-primary:hover")):
                    with self.subTest(state=state):
                        styles = declarations(selector)
                        self.assertIn("background", styles, f"{selector} sem fundo de destaque")
                        self.assertIn("color", styles, f"{selector} sem cor do texto")
                        background = rgb(styles["background"], variables)
                        text = rgb(styles["color"], variables)
                        hue, _, saturation = colorsys.rgb_to_hls(*background)
                        self.assertTrue((hue >= 335 / 360 or hue <= 5 / 360)
                                        and saturation >= 0.5,
                                        f"{theme} {state}: destaque não é vermelho-carmesim: {styles['background']}")
                        self.assertGreaterEqual(contrast(text, background), 4.5,
                                                f"{theme} {state}: texto/botão abaixo de 4.5:1")
                        self.assertGreaterEqual(contrast(background, rgb(variables["--black"], variables)),
                                                3.0, f"{theme} {state}: botão/fundo abaixo de 3:1")

    def test_accent_reaches_navigation_mobile_posts_articles_and_about(self):
        for selector in (".navigation a:hover", ".system-label::before",
                         ".section-index", ".post-category", ".post-link",
                         ".post-entry-content a", ".about-link-arrow"):
            with self.subTest(selector=selector):
                self.assertEqual(declarations(selector).get("color"), "var(--accent)")
        self.assertEqual(declarations(":focus-visible").get("outline"),
                         "1px solid var(--accent)")
        self.assertEqual(declarations(".post-entry-content a").get("text-decoration"),
                         "underline", "Links no texto precisam continuar distinguíveis sem cor")

    def test_brand_icons_and_editorial_mascot_are_not_recolored_by_css(self):
        protected = ("img", ".about-icon", ".about-icon-linkedin-light",
                     ".about-icon-linkedin-dark", ".profile-image img", ".post-entry-art img")
        for selector in protected:
            with self.subTest(selector=selector):
                styles = declarations(selector)
                self.assertFalse({"filter", "mix-blend-mode", "mask", "mask-image"} & styles.keys(),
                                 f"{selector}: imagem oficial/mascote não deve receber recoloração")
        # GitHub is intentionally inverted on dark and restored on light by existing CSS.
        self.assertEqual(declarations(".about-icon-github").get("filter"), "invert(1)")
        self.assertEqual(declarations(':root[data-theme="light"] .about-icon-github').get("filter"), "none")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
