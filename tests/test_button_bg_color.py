import unittest
from unittest.mock import patch

from OpenHeartsMusic import config
from OpenHeartsMusic import __main__ as bot_main
from OpenHeartsMusic.helpers import buttons
from OpenHeartsMusic.helpers._thumbnails import build_now_playing_buttons


class ButtonBackgroundColorTests(unittest.TestCase):
    def test_plugin_loader_imports_discovered_modules(self):
        with patch.object(bot_main.logger, "error") as log_error:
            loaded = bot_main.load_plugins()

        self.assertEqual(loaded, len(bot_main.all_modules) + 1)
        log_error.assert_not_called()

    def test_color_button_adds_visible_background_marker(self):
        original = getattr(config, "BUTTON_BG_COLOR", None)
        try:
            config.BUTTON_BG_COLOR = "green"
            button = buttons.color_button("Help", callback_data="help")
            self.assertEqual(button.text, "Help")
            self.assertEqual(button.callback_data, "help")
        finally:
            if original is None:
                if hasattr(config, "BUTTON_BG_COLOR"):
                    delattr(config, "BUTTON_BG_COLOR")
            else:
                config.BUTTON_BG_COLOR = original

    def test_invalid_color_falls_back_to_default_button_text(self):
        original = getattr(config, "BUTTON_BG_COLOR", None)
        try:
            config.BUTTON_BG_COLOR = "not-a-color"
            button = buttons.color_button("Queue", callback_data="queue")
            self.assertEqual(button.text, "Queue")
        finally:
            if original is None:
                if hasattr(config, "BUTTON_BG_COLOR"):
                    delattr(config, "BUTTON_BG_COLOR")
            else:
                config.BUTTON_BG_COLOR = original

    def test_background_style_aliases_map_to_telegram_styles(self):
        primary = buttons.color_button(
            "Primary Blue", callback_data="primary_blue", style="bg_primary"
        )
        success = buttons.color_button(
            "Success Green", callback_data="success_green", style="bg_success"
        )

        self.assertEqual(primary.style, "primary")
        self.assertEqual(success.style, "success")

    def test_background_color_is_serialized_for_bot_api(self):
        blue = buttons.ikb(
            text="Primary Blue",
            callback_data="primary_blue",
            background_color="blue",
        )
        green = buttons.ikb(
            text="Success Green",
            callback_data="success_green",
            background_color="green",
        )

        self.assertEqual(blue.write()["style"], "primary")
        self.assertEqual(green.write()["style"], "success")

    def test_color_button_accepts_background_color_parameter(self):
        button = buttons.color_button(
            "Download",
            callback_data="download",
            background_color="success",
        )

        self.assertEqual(button.style, "success")
        self.assertEqual(button.write()["style"], "success")

    def test_button_style_accepts_only_supported_variants(self):
        for style in ("danger", "success", "primary"):
            button = buttons.color_button("Action", callback_data="action", style=style)
            self.assertEqual(button.style, style)

        with self.assertRaisesRegex(ValueError, "danger, success, primary"):
            buttons.color_button("Action", callback_data="action", style="secondary")

    def test_now_playing_buttons_use_semantic_styles(self):
        keyboard = build_now_playing_buttons(autoplay_enabled=False)
        styles = [
            button.style
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertEqual(
            styles,
            [
                "primary",
                "success",
                "primary",
                "primary",
                "primary",
                "danger",
                "danger",
                "success",
                "danger",
            ],
        )

        enabled_keyboard = build_now_playing_buttons(autoplay_enabled=True)
        self.assertEqual(enabled_keyboard.inline_keyboard[2][0].style, "success")


if __name__ == "__main__":
    unittest.main()
