"""
Basic unit tests for the Personal Voice Assistant.

Run:
    python test_assistant.py
"""

import sys
import os

# Ensure assistant.py in the same folder is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from assistant import words_in, has_word, to_class_name


# ==================================================
# TESTS
# ==================================================

def test_words_in():
    """Test the words_in() helper."""
    assert words_in("Hello World 123") == {"hello", "world", "123"}
    assert words_in("") == set()
    assert words_in("Open CHROME now!") == {"open", "chrome", "now"}
    print("PASS: test_words_in")


def test_has_word():
    """Test the has_word() helper."""
    assert has_word("open chrome now", "open", "close") is True
    assert has_word("open chrome now", "firefox", "edge") is False
    assert has_word("set alarm for 7 am", "alarm") is True
    print("PASS: test_has_word")


def test_to_class_name():
    """Test the to_class_name() helper for Java file creation."""
    assert to_class_name("hello world") == "HelloWorld"
    assert to_class_name("my java") == "My"
    assert to_class_name("123 abc") == "Program123Abc"
    assert to_class_name("called My Program") == "MyProgram"
    print("PASS: test_to_class_name")


# ==================================================
# RUNNER
# ==================================================

if __name__ == "__main__":
    print("Running tests...\n")

    test_words_in()
    test_has_word()
    test_to_class_name()

    print("\nAll tests passed!")